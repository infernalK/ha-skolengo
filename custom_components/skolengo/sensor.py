"""Sensor platform for Skolengo."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .colors import normalize_color
from .const import CONF_STUDENT_NAME, DOMAIN, MANUFACTURER
from .coordinator import SkolengoDataUpdateCoordinator
from .evaluations import flatten_evaluations as _evaluation_list
from .homework import flatten_homework


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SkolengoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SkolengoStudentClassSensor(coordinator, entry),
            SkolengoNextLessonSensor(coordinator, entry),
            SkolengoNextAlarmSensor(coordinator, entry),
            SkolengoTimetableTodaySensor(coordinator, entry),
            SkolengoTimetableNextDaySensor(coordinator, entry),
            SkolengoTodayLessonCountSensor(coordinator, entry),
            SkolengoHomeworkDueSensor(coordinator, entry),
            SkolengoAbsencesSensor(coordinator, entry),
            SkolengoDelaysSensor(coordinator, entry),
            SkolengoExemptionsSensor(coordinator, entry),
            SkolengoEvaluationsSensor(coordinator, entry),
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

    @property
    def _periods(self) -> list[dict]:
        return self.coordinator.data.periods if self.coordinator.data else []

    @property
    def _student_info(self) -> dict:
        return self.coordinator.data.student_info if self.coordinator.data else {}


class SkolengoStudentClassSensor(SkolengoSensorBase):
    """The student's class (e.g. "4EG2"), with a few other profile details
    as attributes. Refreshed on every coordinator update, so it follows a
    mid-year class change without needing to reconfigure the integration.
    """

    _attr_icon = "mdi:account-school-outline"
    _attr_translation_key = "student_class"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "student_class", "Classe")

    @property
    def native_value(self) -> str | None:
        return self._student_info.get("className")

    @property
    def extra_state_attributes(self) -> dict:
        info = self._student_info
        school = info.get("school") or {}
        return {
            "date_of_birth": info.get("dateOfBirth"),
            "regime": info.get("regime"),
            "school": school.get("name"),
        }


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


class SkolengoNextAlarmSensor(SkolengoSensorBase):
    """When to wake up: first lesson of the next school day, minus a
    configurable lead time (see the integration's Options, default 60 min).
    """

    _attr_icon = "mdi:alarm"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_alarm"

    _FR_WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_alarm", "Prochain réveil")

    @property
    def native_value(self):
        return self.coordinator.data.next_alarm if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict:
        alarm = self.coordinator.data.next_alarm if self.coordinator.data else None
        if not alarm:
            return {}
        local = dt_util.as_local(alarm)
        # A dashboard badge/tile showing this entity's `state` renders a
        # relative time by default (device_class: timestamp) -- this
        # attribute is a literal date+time string, for a badge configured
        # with state_content: ["formatted"] instead. Weekday name is
        # spelled out by hand (not strftime %A) to avoid depending on the
        # host's locale being set to French.
        weekday = self._FR_WEEKDAYS[local.weekday()]
        return {"formatted": f"{weekday} {local.strftime('%d/%m à %H:%M')}"}


def _serialize_lesson(lesson: dict) -> dict:
    return {
        "id": lesson.get("id"),
        "subject": (lesson.get("subject") or {}).get("label") or lesson.get("title"),
        "subject_color": normalize_color((lesson.get("subject") or {}).get("color")),
        "start": lesson.get("startDateTime"),
        "end": lesson.get("endDateTime"),
        "location": lesson.get("location") or lesson.get("room"),
        "canceled": bool(lesson.get("canceled")),
        "teachers": [
            f"{t.get('firstName', '')} {t.get('lastName', '')}".strip()
            for t in (lesson.get("teachers") or [])
        ],
    }


class SkolengoTimetableDaySensorBase(SkolengoSensorBase):
    """Shared day-grouping logic for the two timetable-by-day sensors."""

    def _lessons_by_day(self) -> dict:
        by_day: dict = {}
        for lesson in self._lessons:
            start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
            if not start:
                continue
            start = dt_util.as_local(start)
            by_day.setdefault(start.date(), []).append(lesson)
        return by_day

    def _lessons_for(self, day) -> list[dict]:
        lessons = self._lessons_by_day().get(day, [])
        return sorted(lessons, key=lambda lesson: lesson.get("startDateTime") or "")


class SkolengoTimetableTodaySensor(SkolengoTimetableDaySensorBase):
    """Today's full schedule, regardless of whether the day is already
    over (unlike `timetable_next_day`, this never rolls over to
    tomorrow) -- for a card that should always show "today", e.g. on a
    wall-mounted dashboard.
    """

    _attr_icon = "mdi:calendar-today-outline"
    _attr_native_unit_of_measurement = "cours"
    _attr_translation_key = "timetable_today"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "timetable_today", "Emploi du temps (aujourd'hui)")

    @property
    def native_value(self) -> int:
        return len(self._lessons_for(dt_util.now().date()))

    @property
    def extra_state_attributes(self) -> dict:
        today = dt_util.now().date()
        return {
            "day": today.isoformat(),
            "lessons": [_serialize_lesson(lesson) for lesson in self._lessons_for(today)],
        }


class SkolengoTimetableNextDaySensor(SkolengoTimetableDaySensorBase):
    """Full schedule for the next day after today that actually has
    lessons (skipping weekends/holidays, which simply have none).

    Always strictly after today -- e.g. on a Friday this rolls over to
    Monday, not back to Friday's own remaining lessons. Exists so the
    bundled `skolengo-timetable-card` can render a day's timetable
    without talking to the Calendar API.
    """

    _attr_icon = "mdi:timetable"
    _attr_native_unit_of_measurement = "cours"
    _attr_translation_key = "timetable_next_day"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "timetable_next_day", "Emploi du temps (jour suivant)")

    @property
    def native_value(self) -> int:
        return len(self._day_lessons())

    @property
    def extra_state_attributes(self) -> dict:
        lessons = self._day_lessons()
        day = self._chosen_day()
        return {
            "day": day.isoformat() if day else None,
            "lessons": [_serialize_lesson(lesson) for lesson in lessons],
        }

    def _chosen_day(self):
        today = dt_util.now().date()
        by_day = self._lessons_by_day()
        for day in sorted(by_day):
            if day > today:
                return day
        return None

    def _day_lessons(self) -> list[dict]:
        day = self._chosen_day()
        if day is None:
            return []
        return self._lessons_for(day)


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
        homework_sorted = sorted(
            self._homework, key=lambda hw: hw.get("dueDate") or hw.get("dueDateTime") or ""
        )
        return {
            "assignments": [flatten_homework(hw) for hw in homework_sorted if not hw.get("done")][:30],
            "done_assignments": [flatten_homework(hw) for hw in homework_sorted if hw.get("done")][:30],
        }


def _serialize_absence_file(absence: dict) -> dict:
    """Flatten one Skolengo `/absence-files` record.

    The real field names (confirmed against the reference API client's
    TypeScript models, since Skolengo's own docs don't cover this) live
    under `currentState`: `absenceType` (one of ABSENCE / LATENESS /
    EXEMPTION / DEPARTURE), `absenceStartDateTime`, `absenceEndDateTime`,
    `absenceFileStatus` (NEW / IN_PROGRESS / LOCKED / ...), `comment`, and
    `absenceReason.longLabel`/`.code`.
    """
    state = absence.get("currentState") or {}
    reason = state.get("absenceReason") or {}
    return {
        "id": absence.get("id"),
        "type": state.get("absenceType"),
        "start": state.get("absenceStartDateTime"),
        "end": state.get("absenceEndDateTime"),
        "status": state.get("absenceFileStatus"),
        "reason": reason.get("longLabel"),
        "reason_code": reason.get("code"),
        "comment": state.get("comment"),
    }


class SkolengoAbsencesSensor(SkolengoSensorBase):
    """Number of recorded absences (`absenceType` == ABSENCE).

    Skolengo's `/absence-files` endpoint is actually a unified "vie
    scolaire" log covering absences, lateness ("retards") and exemptions
    ("dispenses") -- see `SkolengoDelaysSensor` and
    `SkolengoExemptionsSensor` below, which read the same underlying data
    filtered by type. Note: "observations", "punitions" and "sanctions"
    (visible on the full Skolengo web portal) are NOT covered by this
    endpoint and don't appear to be exposed by the API this integration
    uses at all -- they may only exist through the school's separate
    Kosmos ENT web pages, not the mobile-app API this integration talks to.
    """

    _attr_icon = "mdi:account-off-outline"
    _attr_native_unit_of_measurement = "absences"
    _attr_translation_key = "absences"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "absences", "Absences")

    def _filtered(self) -> list[dict]:
        return [a for a in self._absences if (a.get("currentState") or {}).get("absenceType") == "ABSENCE"]

    @property
    def native_value(self) -> int:
        return len(self._filtered())

    @property
    def extra_state_attributes(self) -> dict:
        return {"absences": [_serialize_absence_file(a) for a in self._filtered()[:30]]}


class SkolengoDelaysSensor(SkolengoSensorBase):
    """Number of recorded lateness ("retards") records."""

    _attr_icon = "mdi:clock-alert-outline"
    _attr_native_unit_of_measurement = "retards"
    _attr_translation_key = "delays"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "delays", "Retards")

    def _filtered(self) -> list[dict]:
        return [a for a in self._absences if (a.get("currentState") or {}).get("absenceType") == "LATENESS"]

    @property
    def native_value(self) -> int:
        return len(self._filtered())

    @property
    def extra_state_attributes(self) -> dict:
        return {"delays": [_serialize_absence_file(a) for a in self._filtered()[:30]]}


class SkolengoExemptionsSensor(SkolengoSensorBase):
    """Number of recorded exemptions ("dispenses", e.g. from PE)."""

    _attr_icon = "mdi:hand-back-right-off-outline"
    _attr_native_unit_of_measurement = "dispenses"
    _attr_translation_key = "exemptions"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "exemptions", "Dispenses")

    def _filtered(self) -> list[dict]:
        return [a for a in self._absences if (a.get("currentState") or {}).get("absenceType") == "EXEMPTION"]

    @property
    def native_value(self) -> int:
        return len(self._filtered())

    @property
    def extra_state_attributes(self) -> dict:
        return {"exemptions": [_serialize_absence_file(a) for a in self._filtered()[:30]]}


def _average_mark(items: list[dict]) -> float | None:
    """Naive average of the numeric `mark`s in a flattened evaluation
    list (skill-based evaluations, which have no `mark`, are excluded).

    This treats every mark as equally weighted, which is NOT how a real
    school average works (a 5-point quiz and a 20-point exam don't count
    the same). Only used as a fallback when Skolengo doesn't return a
    `studentAverage` at all -- see _official_average(), which should
    always be preferred when available.
    """
    grades = [item["mark"] for item in items if item["mark"] is not None]
    if not grades:
        return None
    return round(sum(grades) / len(grades), 2)


def _official_average(evaluation_services: list[dict]) -> float | None:
    """Skolengo's own coefficient-weighted average across subjects,
    built from each `evaluationService.studentAverage` -- the real,
    official average, as opposed to `_average_mark()`'s naive mean of
    individual marks.
    """
    weighted_sum = 0.0
    total_coefficient = 0.0
    for service in evaluation_services:
        avg = service.get("studentAverage")
        if not isinstance(avg, (int, float)):
            continue
        coefficient = service.get("coefficient")
        coefficient = float(coefficient) if isinstance(coefficient, (int, float)) and coefficient > 0 else 1.0
        weighted_sum += float(avg) * coefficient
        total_coefficient += coefficient
    if total_coefficient == 0:
        return None
    return round(weighted_sum / total_coefficient, 2)


def _periods_meta(periods: list[dict]) -> list[dict]:
    """Serialize periods (trimesters/semesters) for the card's selector,
    sorted chronologically with the currently-active one flagged.
    """
    today = dt_util.now().date().isoformat()
    result = [
        {
            "id": period.get("id"),
            "label": period.get("label"),
            "start_date": period.get("startDate"),
            "end_date": period.get("endDate"),
            "current": bool(
                period.get("startDate")
                and period.get("endDate")
                and period["startDate"] <= today <= period["endDate"]
            ),
        }
        for period in periods
    ]
    result.sort(key=lambda p: p["start_date"] or "")
    return result


def _group_services_by_period(evaluation_services: list[dict]) -> dict[str, list[dict]]:
    """Split evaluationService records back out by the period id the
    coordinator tagged them with when fetching one period at a time.
    """
    grouped: dict[str, list[dict]] = {}
    for service in evaluation_services:
        period_id = service.get("_period_id")
        if period_id:
            grouped.setdefault(period_id, []).append(service)
    return grouped


class SkolengoEvaluationsSensor(SkolengoSensorBase):
    """Number of recorded evaluations/grades, with the full list (used by
    the bundled `skolengo-evaluations-card`) as an attribute.

    Some schools' grade endpoints are known to be flaky or unsupported by
    Skolengo for certain establishments; in that case this sensor will
    simply report 0 with an empty list.
    """

    _attr_icon = "mdi:notebook-outline"
    _attr_native_unit_of_measurement = "notes"
    _attr_translation_key = "evaluations"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "evaluations", "Notes")

    def _items(self) -> list[dict]:
        items = _evaluation_list(self._evaluations)
        items.sort(key=lambda item: item["date"] or "", reverse=True)
        return items

    @property
    def native_value(self) -> int:
        return len(self._items())

    @property
    def extra_state_attributes(self) -> dict:
        items = self._items()
        official = _official_average(self._evaluations)
        by_period: dict[str, dict] = {}
        for period_id, services in _group_services_by_period(self._evaluations).items():
            period_items = sorted(
                (item for item in items if item.get("period_id") == period_id),
                key=lambda item: item["date"] or "",
                reverse=True,
            )
            period_official = _official_average(services)
            by_period[period_id] = {
                "evaluations": period_items[:30],
                "average": period_official if period_official is not None else _average_mark(period_items),
            }
        return {
            "evaluations": items[:30],
            "average": official if official is not None else _average_mark(items),
            "periods": _periods_meta(self._periods),
            "evaluations_by_period": by_period,
        }


def _subject_averages(evaluation_services: list[dict]) -> list[dict]:
    """Per-subject breakdown of the official average, for use alongside
    `_official_average()`'s overall figure.

    Skolengo can return one `evaluationService` per (subject, period)
    pair, so a subject followed over several periods may appear more
    than once in `evaluation_services`; entries sharing the same subject
    are combined the same way `_official_average()` combines subjects
    (coefficient-weighted), so each subject appears exactly once here.
    """
    by_subject: dict[str, dict] = {}
    order: list[str] = []
    for service in evaluation_services:
        subject = service.get("subject") or {}
        key = subject.get("id") or subject.get("label")
        if not key:
            continue
        if key not in by_subject:
            by_subject[key] = {
                "subject": subject.get("label"),
                "subject_color": normalize_color(subject.get("color")),
                "weighted_sum": 0.0,
                "total_coefficient": 0.0,
                "class_weighted_sum": 0.0,
                "class_total_coefficient": 0.0,
            }
            order.append(key)
        entry = by_subject[key]

        coefficient = service.get("coefficient")
        coefficient = float(coefficient) if isinstance(coefficient, (int, float)) and coefficient > 0 else 1.0

        avg = service.get("studentAverage")
        if isinstance(avg, (int, float)):
            entry["weighted_sum"] += float(avg) * coefficient
            entry["total_coefficient"] += coefficient

        class_avg = service.get("average")
        if isinstance(class_avg, (int, float)):
            entry["class_weighted_sum"] += float(class_avg) * coefficient
            entry["class_total_coefficient"] += coefficient

    result = []
    for key in order:
        entry = by_subject[key]
        average = (
            round(entry["weighted_sum"] / entry["total_coefficient"], 2)
            if entry["total_coefficient"]
            else None
        )
        class_average = (
            round(entry["class_weighted_sum"] / entry["class_total_coefficient"], 2)
            if entry["class_total_coefficient"]
            else None
        )
        result.append(
            {
                "subject": entry["subject"],
                "subject_color": entry["subject_color"],
                "average": average,
                "class_average": class_average,
            }
        )
    return result


class SkolengoAverageGradeSensor(SkolengoSensorBase):
    """Overall average grade.

    Prefers Skolengo's own officially-computed, coefficient-weighted
    average (`evaluationService.studentAverage`, see
    `_official_average()`); falls back to a naive mean of individual
    marks only if the school's API doesn't populate that field at all.
    Same value as the "Notes" sensor's `average` attribute, exposed here
    as its own entity for history graphing / automations. Some schools'
    grade endpoints are known to be flaky or unsupported by Skolengo for
    certain establishments; in that case this sensor will simply report
    `unknown`.

    The per-subject breakdown (`by_subject`, see `_subject_averages()`)
    is only available when Skolengo's officially-computed averages are
    present, since it wouldn't otherwise be meaningful to combine with
    the naive fallback used for the overall state.
    """

    _attr_icon = "mdi:school-outline"
    _attr_translation_key = "average_grade"

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "average_grade", "Moyenne générale")

    @property
    def native_value(self) -> float | None:
        official = _official_average(self._evaluations)
        if official is not None:
            return official
        return _average_mark(_evaluation_list(self._evaluations))

    @property
    def extra_state_attributes(self) -> dict:
        by_period: dict[str, dict] = {}
        for period_id, services in _group_services_by_period(self._evaluations).items():
            period_official = _official_average(services)
            by_period[period_id] = {
                "average": period_official,
                "by_subject": _subject_averages(services),
            }
        return {
            "by_subject": _subject_averages(self._evaluations),
            "periods": _periods_meta(self._periods),
            "average_by_period": by_period,
        }
