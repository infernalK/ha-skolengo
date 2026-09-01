"""The Skolengo integration."""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
    hass.data[_FRONTEND_REGISTERED_KEY] = True

    www_dir = os.path.join(os.path.dirname(__file__), "www")

    try:
        # Current, non-deprecated API (HA 2024.7+).
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_PATH, www_dir, cache_headers=False)]
        )
    except ImportError:
        # Fallback for older Home Assistant Core versions.
        hass.http.register_static_path(STATIC_PATH, www_dir, cache_headers=False)

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{STATIC_PATH}/{JS_FILENAME}")
    except ImportError:
        _LOGGER.warning(
            "Impossible d'enregistrer automatiquement les cartes Lovelace Skolengo "
            "(module frontend indisponible) ; ajoutez %s/%s comme ressource "
            "manuellement si besoin.",
            STATIC_PATH,
            JS_FILENAME,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Skolengo from a config entry."""
    await _async_register_frontend(hass)

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
