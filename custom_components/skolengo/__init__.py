"""The Skolengo integration."""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.loader import async_get_integration

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import SkolengoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Bundled Lovelace cards (see custom_components/skolengo/www/skolengo-cards.js):
# served as a static path and auto-registered as a frontend JS module, so
# users don't have to add a Lovelace resource by hand.
STATIC_PATH = "/skolengo_static"
JS_FILENAME = "skolengo-cards.js"
_FRONTEND_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


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
    js_url = f"{STATIC_PATH}/{JS_FILENAME}?v={integration.version}"

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


# Debug service: Skolengo's "vie scolaire" observations/punishments are not
# covered by any documented endpoint, so this tries candidate paths and
# reports the raw HTTP status/body of each (404 = does not exist).
PROBE_CANDIDATES = [
    "/sko-app-configs/current",
    "/school-life",
    "/school-life-events",
    "/school-life-files",
    "/school-life-summary",
    "/school-life-reports",
    "/observations",
    "/observation-files",
    "/punishments",
    "/punishment-files",
    "/sanctions",
    "/sanction-files",
    "/incidents",
    "/incident-files",
    "/behaviors",
    "/behaviours",
    "/disciplinary-files",
    "/disciplinary-measures",
    "/student-observations",
    "/student-punishments",
    "/lateness-files",
    "/absence-files-summary",
    "/absence-counters",
]
SERVICE_PROBE = "probe_endpoints"


async def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_PROBE):
        return

    async def _probe(call: ServiceCall) -> dict:
        paths = call.data.get("paths") or PROBE_CANDIDATES
        entry_id = call.data.get("entry_id")
        coordinators = hass.data.get(DOMAIN, {})
        coordinator = coordinators.get(entry_id) if entry_id else next(iter(coordinators.values()), None)
        if coordinator is None:
            return {"error": "no Skolengo entry loaded"}
        results = []
        for path in paths:
            # A path carrying its own query string is sent as-is; "{student}"
            # in it is replaced by the student id.
            if "?" in path:
                path = path.replace("{student}", coordinator.student_id)
                params = None
            else:
                params = {"filter[student.id]": coordinator.student_id}
            result = await hass.async_add_executor_job(coordinator.client.probe, path, params)
            if params and result.get("status") in (400, 422):
                result = await hass.async_add_executor_job(coordinator.client.probe, path, None)
            _LOGGER.warning("Skolengo probe %s -> %s %s", path, result.get("status"), (result.get("body") or result.get("error") or "")[:500])
            results.append(result)
        return {"results": results}

    hass.services.async_register(
        DOMAIN, SERVICE_PROBE, _probe, supports_response=SupportsResponse.ONLY
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Skolengo from a config entry."""
    await _async_register_frontend(hass)
    await _async_register_services(hass)

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


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
