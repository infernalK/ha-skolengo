"""Binary sensor platform for Skolengo."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STUDENT_NAME, DOMAIN, MANUFACTURER
from .coordinator import SkolengoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SkolengoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SkolengoReauthRequiredBinarySensor(coordinator, entry)])


class SkolengoReauthRequiredBinarySensor(
    CoordinatorEntity[SkolengoDataUpdateCoordinator], BinarySensorEntity
):
    """On while Skolengo rejects the stored credentials and the user has to
    sign in again. Meant to trigger an automation (e.g. a phone notification).
    Stays available when the data is not, unlike the other entities."""

    _attr_has_entity_name = True
    _attr_translation_key = "reauth_required"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reauth_required"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Skolengo - {entry.data.get(CONF_STUDENT_NAME, entry.title)}",
            manufacturer=MANUFACTURER,
            entry_type="service",
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.auth_failed
