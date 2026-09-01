"""Calendar platform for Skolengo: timetable (lessons) and homework due dates."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_STUDENT_ID, CONF_STUDENT_NAME, DOMAIN, MANUFACTURER
from .coordinator import SkolengoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SkolengoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SkolengoTimetableCalendar(coordinator, entry),
            SkolengoHomeworkCalendar(coordinator, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Skolengo - {entry.data.get(CONF_STUDENT_NAME, entry.title)}",
        manufacturer=MANUFACTURER,
        entry_type="service",
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_local(parsed)


def _lesson_summary(lesson: dict) -> str:
    subject = lesson.get("subject") or {}
    title = subject.get("label") or lesson.get("title") or "Cours"
    if lesson.get("canceled"):
        return f"[Annulé] {title}"
    return title


def _lesson_description(lesson: dict) -> str:
    parts = []
    teachers = lesson.get("teachers") or []
    if teachers:
        names = ", ".join(
            f"{t.get('firstName', '')} {t.get('lastName', '')}".strip() for t in teachers
        )
        if names.strip():
            parts.append(f"Professeur(s): {names}")
    if lesson.get("content"):
        parts.append(str(lesson["content"]))
    return "\n".join(parts)


class SkolengoTimetableCalendar(
    CoordinatorEntity[SkolengoDataUpdateCoordinator], CalendarEntity
):
    """Calendar entity exposing the student's timetable."""

    _attr_has_entity_name = True
    _attr_translation_key = "timetable"
    _attr_icon = "mdi:timetable"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_timetable"
        self._attr_device_info = _device_info(entry)
        self._attr_name = "Emploi du temps"

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming = self._events_between(now, now + timedelta(days=30))
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date, end_date)

    def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for lesson in self.coordinator.data.lessons if self.coordinator.data else []:
            lesson_start = _parse_dt(lesson.get("startDateTime"))
            lesson_end = _parse_dt(lesson.get("endDateTime"))
            if not lesson_start or not lesson_end:
                continue
            if lesson_end < start or lesson_start > end:
                continue
            location = lesson.get("location") or lesson.get("room") or ""
            events.append(
                CalendarEvent(
                    start=lesson_start,
                    end=lesson_end,
                    summary=_lesson_summary(lesson),
                    description=_lesson_description(lesson),
                    location=str(location) if location else None,
                    uid=str(lesson.get("id")) if lesson.get("id") else None,
                )
            )
        events.sort(key=lambda e: e.start)
        return events


class SkolengoHomeworkCalendar(
    CoordinatorEntity[SkolengoDataUpdateCoordinator], CalendarEntity
):
    """Calendar entity exposing homework due dates as all-day events."""

    _attr_has_entity_name = True
    _attr_translation_key = "homework"
    _attr_icon = "mdi:notebook-edit-outline"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_homework"
        self._attr_device_info = _device_info(entry)
        self._attr_name = "Devoirs"

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now()
        upcoming = self._events_between(today, today + timedelta(days=60))
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date, end_date)

    def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for hw in self.coordinator.data.homework if self.coordinator.data else []:
            due_raw = hw.get("dueDate")
            if not due_raw:
                continue
            try:
                due_date = dt_util.parse_date(due_raw) or _parse_dt(due_raw).date()
            except Exception:  # noqa: BLE001
                continue
            due_start = dt_util.start_of_local_day(
                datetime.combine(due_date, datetime.min.time())
            )
            due_end = due_start + timedelta(days=1)
            if due_end < start or due_start > end:
                continue
            subject = hw.get("subject") or {}
            title = subject.get("label") or "Devoir"
            done = " (fait)" if hw.get("done") else ""
            events.append(
                CalendarEvent(
                    start=due_start.date(),
                    end=due_end.date(),
                    summary=f"{title}{done}",
                    description=str(hw.get("assignmentText") or hw.get("html") or ""),
                    uid=str(hw.get("id")) if hw.get("id") else None,
                )
            )
        events.sort(key=lambda e: e.start)
        return events
