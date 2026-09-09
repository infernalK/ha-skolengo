"""Diagnostics support for Skolengo.

Redacts the refresh token and the student's own identifying fields
(name, date of birth, photo) before the dump is handed to the user for
download -- everything else (lessons, homework, grades structure) is
kept as-is since that's exactly the raw shape needed to debug parsing
bugs like the ones already fixed in this integration (grades stuck on
"Non noté", inconsistent subject colors, ...).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SkolengoDataUpdateCoordinator

TO_REDACT_ENTRY = {"refresh_token", "user_id"}
TO_REDACT_DATA = {"firstName", "lastName", "dateOfBirth", "photoUrl", "student_name"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Skolengo config entry."""
    coordinator: SkolengoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT_ENTRY),
        "entry_options": dict(entry.options),
        "coordinator_data": async_redact_data(
            {
                "lessons": data.lessons,
                "homework": data.homework,
                "absences": data.absences,
                "evaluations": data.evaluations,
                "periods": data.periods,
                "student_info": data.student_info,
                "next_alarm": data.next_alarm.isoformat() if data.next_alarm else None,
            }
            if data
            else None,
            TO_REDACT_DATA,
        ),
    }
