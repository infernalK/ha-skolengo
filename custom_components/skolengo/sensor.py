"""Sensor platform for Skolengo."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_STUDENT_NAME, DOMAIN, MANUFACTURER
from .coordinator import SkolengoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SkolengoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SkolengoNextLessonSensor(coordinator, entry),
            SkolengoTodayLessonCountSensor(coordinator, entry),
            SkolengoHomeworkDueSensor(coordinator, entry),
            SkolengoAbsencesSensor(coordinator, entry),
            SkolengoAverageGradeSensor(coordinator, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Skolengo - {entry.data.get(CONF_STUDENT_NAME, entry.title)}",
        manufacturer=MANUFACTURER,
        entry_type="service",
    )


class SkolengoSensorBase(CoordinatorEntity[SkolengoDataUpdateCoordinator], SensorEntity):
    """Common base for Skolengo sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)
        self._attr_name = name

    @property
    def _lessons(self) -> list[dict]:
        return self.coordinator.data.lessons if self.coordinator.data else []

    @property
    def _homework(self) -> list[dict]:
        return self.coordinator.data.homework if self.coordinator.data else []

    @property
    def _absences(self) -> list[dict]:
        return self.coordinator.data.absences if self.coordinator.data else []

    @property
    def _evaluations(self) -> list[dict]:
        return self.coordinator.data.evaluations if self.coordinator.data else []


class SkolengoNextLessonSensor(SkolengoSensorBase):
    """Next upcoming (non-canceled) lesson."""

    _attr_icon = "mdi:book-open-variant"
    _attr_translation_key = "next_lesson"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_lesson", "Prochain cours")

    @property
    def native_value(self) -> str | None:
        lesson = self._next_lesson()
        if not lesson:
            return None
        subject = lesson.get("subject") or {}
        return subject.get("label") or lesson.get("title") or "Cours"

    @property
    def extra_state_attributes(self) -> dict:
        lesson = self._next_lesson()
        if not lesson:
            return {}
        return {
            "start": lesson.get("startDateTime"),
            "end": lesson.get("endDateTime"),
            "location": lesson.get("location") or lesson.get("room"),
            "canceled": lesson.get("canceled", False),
        }

    def _next_lesson(self) -> dict | None:
        now = dt_util.utcnow()
        upcoming = []
        for lesson in self._lessons:
            if lesson.get("canceled"):
                continue
            start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
            if not start:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            if start >= now:
                upcoming.append((start, lesson))
        if not upcoming:
            return None
        upcoming.sort(key=lambda item: item[0])
        return upcoming[0][1]


class SkolengoTodayLessonCountSensor(SkolengoSensorBase):
    """Number of lessons scheduled today."""

    _attr_icon = "mdi:calendar-today"
    _attr_native_unit_of_measurement = "cours"
    _attr_translation_key = "today_lesson_count"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_lesson_count", "Cours aujourd'hui")

    @property
    def native_value(self) -> int:
        today = dt_util.now().date()
        count = 0
        for lesson in self._lessons:
            if lesson.get("canceled"):
                continue
            start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
            if start and dt_util.as_local(start).date() == today:
                count += 1
        return count


class SkolengoHomeworkDueSensor(SkolengoSensorBase):
    """Number of not-yet-done homework assignments due soon."""

    _attr_icon = "mdi:notebook-edit-outline"
    _attr_native_unit_of_measurement = "devoirs"
    _attr_translation_key = "homework_due"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "homework_due", "Devoirs à faire")

    @property
    def native_value(self) -> int:
        return sum(1 for hw in self._homework if not hw.get("done"))

    @property
    def extra_state_attributes(self) -> dict:
        pending = [hw for hw in self._homework if not hw.get("done")]
        return {
            "assignments": [
                {
                    "subject": (hw.get("subject") or {}).get("label"),
                    "due_date": hw.get("dueDate"),
                }
                for hw in pending[:20]
            ]
        }


class SkolengoAbsencesSensor(SkolengoSensorBase):
    """Number of recorded absence files."""

    _attr_icon = "mdi:account-off-outline"
    _attr_native_unit_of_measurement = "absences"
    _attr_translation_key = "absences"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "absences", "Absences")

    @property
    def native_value(self) -> int:
        return len(self._absences)


class SkolengoAverageGradeSensor(SkolengoSensorBase):
    """Best-effort overall average grade.

    Some schools' grade endpoints are known to be flaky or unsupported by
    Skolengo for certain establishments; in that case this sensor will
    simply report `unknown`.
    """

    _attr_icon = "mdi:school-outline"
    _attr_translation_key = "average_grade"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "average_grade", "Moyenne générale")

    @property
    def native_value(self) -> float | None:
        grades: list[float] = []
        for evaluation_service in self._evaluations:
            for evaluation in evaluation_service.get("evaluations") or []:
                for result in evaluation.get("evaluationResults") or []:
                    value = result.get("nonEvaluated") is not True and result.get("value")
                    if isinstance(value, (int, float)):
                        grades.append(float(value))
        if not grades:
            return None
        return round(sum(grades) / len(grades), 2)
