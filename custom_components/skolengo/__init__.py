"""The Skolengo integration."""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .const import CONF_SCAN_INTERVAL, CONF_SCHOOL_ID, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import CACHE_STORAGE_VERSION, SkolengoDataUpdateCoordinator
from .news import release_news_sensor
from .news_files import SkolengoNewsFileView

_LOGGER = logging.getLogger(__name__)

# Bundled Lovelace cards (see custom_components/skolengo/www/skolengo-cards.js):
# served as a static path and auto-registered as a frontend JS module, so
# users don't have to add a Lovelace resource by hand.
STATIC_PATH = "/skolengo_static"
JS_FILENAME = "skolengo-cards.js"
_FRONTEND_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"
_VIEW_REGISTERED_KEY = f"{DOMAIN}_news_view_registered"


def _file_hash(path: str) -> str:
    """Short content hash of a file (empty string if unreadable)."""
    try:
        with open(path, "rb") as file:
            return hashlib.sha256(file.read()).hexdigest()[:8]
    except OSError:
        return ""


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled skolengo-cards.js and auto-load it as a Lovelace
    resource, once per Home Assistant run (guarded, since this integration
    supports several config entries — one per child).
    """
    if hass.data.get(_FRONTEND_REGISTERED_KEY):
        return

    www_dir = os.path.join(os.path.dirname(__file__), "www")

    # The URL below is cache-busted with the integration's own version
    # (?v=...), so it's safe -- and desirable -- to let browsers cache the
    # response aggressively: a version bump always gets a brand new URL, so
    # a stale cached copy can never be served across an update. Conversely,
    # *without* long-lived caching here, every dashboard load has to reach
    # the HA server over the network for this file, even for a version
    # that's already been fetched -- so a transient network hiccup (e.g. on
    # a mobile connection) can make every bundled card fail at once, until
    # the browser retries successfully.
    try:
        # Current, non-deprecated API (HA 2024.7+).
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_PATH, www_dir, cache_headers=True)]
        )
    except ImportError:
        # Fallback for older Home Assistant Core versions.
        hass.http.register_static_path(STATIC_PATH, www_dir, cache_headers=True)

    integration = await async_get_integration(hass, DOMAIN)
    # Cache-bust with the file's content hash as well as the version: the
    # mobile apps' webviews cache this file very aggressively, and a JS
    # change shipped without a version bump would otherwise keep serving the
    # stale copy (cards missing / "custom element doesn't exist") even after
    # clearing the app cache.
    js_hash = await hass.async_add_executor_job(_file_hash, os.path.join(www_dir, JS_FILENAME))
    js_url = f"{STATIC_PATH}/{JS_FILENAME}?v={integration.version}-{js_hash}"

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, js_url)
    except ImportError:
        _LOGGER.warning(
            "Impossible d'enregistrer automatiquement les cartes Lovelace Skolengo "
            "(module frontend indisponible) ; ajoutez %s comme ressource "
            "manuellement si besoin.",
            js_url,
        )
        return

    hass.data[_FRONTEND_REGISTERED_KEY] = True

    # The extra JS URL above is baked into the frontend's index page, which
    # the iOS/Android companion apps may keep cached for a long time. A
    # Lovelace resource is fetched fresh over the websocket every time a
    # dashboard loads, so also register one (storage mode only). The script
    # is idempotent (safeDefine), so loading it twice is harmless.
    async def _register_resource(_event=None) -> None:
        try:
            await _async_ensure_lovelace_resource(hass, js_url)
        except Exception:  # noqa: BLE001 - never break setup over this
            _LOGGER.debug("Enregistrement de la ressource Lovelace impossible", exc_info=True)

    if hass.is_running:
        await _register_resource()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_resource)


async def _async_ensure_lovelace_resource(hass: HomeAssistant, js_url: str) -> None:
    """Create or update the Lovelace resource pointing at the bundled cards."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return
    if isinstance(lovelace, dict):  # Home Assistant < 2024.x
        mode, resources = lovelace.get("mode"), lovelace.get("resources")
    else:
        mode = getattr(lovelace, "resource_mode", getattr(lovelace, "mode", None))
        resources = getattr(lovelace, "resources", None)
    if mode != "storage" or resources is None or not hasattr(resources, "async_create_item"):
        return  # YAML mode: the user manages resources by hand

    await resources.async_get_info()  # makes sure the collection is loaded
    base = f"{STATIC_PATH}/{JS_FILENAME}"
    for item in resources.async_items():
        if item["url"].split("?")[0] == base:
            if item["url"] != js_url or item.get("type") != "module":
                await resources.async_update_item(
                    item["id"], {"res_type": "module", "url": js_url}
                )
            return
    await resources.async_create_item({"res_type": "module", "url": js_url})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Skolengo from a config entry."""
    await _async_register_frontend(hass)
    if not hass.data.get(_VIEW_REGISTERED_KEY):
        hass.http.register_view(SkolengoNewsFileView())
        hass.data[_VIEW_REGISTERED_KEY] = True

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SkolengoDataUpdateCoordinator(
        hass, entry, update_interval=timedelta(minutes=scan_interval)
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the persisted last-known-data cache of a removed entry."""
    await Store(hass, CACHE_STORAGE_VERSION, f"{DOMAIN}_cache_{entry.entry_id}").async_remove()


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        school_id = entry.data[CONF_SCHOOL_ID]
        if release_news_sensor(hass, school_id, entry.entry_id):
            # This entry owned the school's news sensor: let a sibling entry
            # of the same school take it over.
            for other in hass.config_entries.async_loaded_entries(DOMAIN):
                if other.entry_id != entry.entry_id and other.data.get(CONF_SCHOOL_ID) == school_id:
                    hass.config_entries.async_schedule_reload(other.entry_id)
                    break
    return unload_ok
