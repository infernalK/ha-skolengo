"""Sensor platform for Skolengo."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
            SkolengoStudentClassSensor(coordinator, entry),
            SkolengoNextLessonSensor(coordinator, entry),
            SkolengoNextAlarmSensor(coordinator, entry),
            SkolengoTimetableNextDaySensor(coordinator, entry),
            SkolengoTodayLessonCountSensor(coordinator, entry),
            SkolengoHomeworkDueSensor(coordinator, entry),
            SkolengoAbsencesSensor(coordinator, entry),
            SkolengoDelaysSensor(coordinator, entry),
            SkolengoExemptionsSensor(coordinator, entry),
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

    def __init__(self, coordinator: SkolengoDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_alarm", "Prochain réveil")

    @property
    def native_value(self):
        return self.coordinator.data.next_alarm if self.coordinator.data else None


class SkolengoTimetableNextDaySensor(SkolengoSensorBase):
    """Full schedule for the "next" school day: today's remaining lessons
    if the day isn't over yet, otherwise the next day that has lessons.

    Exists so the bundled `skolengo-timetable-card` can render a day's
    timetable without talking to the Calendar API.
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
            "lessons": [
                {
                    "id": lesson.get("id"),
                    "subject": (lesson.get("subject") or {}).get("label") or lesson.get("title"),
                    "subject_color": (lesson.get("subject") or {}).get("color"),
                    "start": lesson.get("startDateTime"),
                    "end": lesson.get("endDateTime"),
                    "location": lesson.get("location") or lesson.get("room"),
                    "canceled": bool(lesson.get("canceled")),
                    "teachers": [
                        f"{t.get('firstName', '')} {t.get('lastName', '')}".strip()
                        for t in (lesson.get("teachers") or [])
                    ],
                }
                for lesson in lessons
            ],
        }

    def _lessons_by_day(self) -> dict:
        by_day: dict = {}
        for lesson in self._lessons:
            start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
            if not start:
                continue
            start = dt_util.as_local(start)
            by_day.setdefault(start.date(), []).append(lesson)
        return by_day

    def _chosen_day(self):
        now = dt_util.now()
        by_day = self._lessons_by_day()
        for day in sorted(by_day):
            if day < now.date():
                continue
            if day == now.date():
                has_remaining = any(
                    (dt_util.as_local(dt_util.parse_datetime(lesson["startDateTime"])) >= now)
                    for lesson in by_day[day]
                    if lesson.get("startDateTime") and not lesson.get("canceled")
                )
                if not has_remaining:
                    continue
            return day
        return None

    def _day_lessons(self) -> list[dict]:
        day = self._chosen_day()
        if day is None:
            return []
        lessons = self._lessons_by_day().get(day, [])
        return sorted(lessons, key=lambda lesson: lesson.get("startDateTime") or "")


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
        def _serialize(hw: dict) -> dict:
            subject = hw.get("subject") or {}
            teacher = hw.get("teacher") or {}
            return {
                "id": hw.get("id"),
                "subject": subject.get("label"),
                "subject_color": subject.get("color"),
                "due_date": hw.get("dueDate") or hw.get("dueDateTime"),
                "done": bool(hw.get("done")),
                "title": hw.get("title"),
                "html": hw.get("html"),
                "teacher": f"{teacher.get('firstName', '')} {teacher.get('lastName', '')}".strip() or None,
            }

        homework_sorted = sorted(
            self._homework, key=lambda hw: hw.get("dueDate") or hw.get("dueDateTime") or ""
        )
        return {
            "assignments": [_serialize(hw) for hw in homework_sorted if not hw.get("done")][:30],
            "done_assignments": [_serialize(hw) for hw in homework_sorted if hw.get("done")][:30],
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
        grades = [item["mark"] for item in self._evaluation_list() if item["mark"] is not None]
        if not grades:
            return None
        return round(sum(grades) / len(grades), 2)

    @property
    def extra_state_attributes(self) -> dict:
        items = self._evaluation_list()
        items.sort(key=lambda item: item["date"] or "", reverse=True)
        return {"evaluations": items[:30]}

    def _evaluation_list(self) -> list[dict]:
        """Flatten evaluation-services -> evaluations into one list.

        Skolengo doesn't separate "grades" (numeric) from "evaluations"
        (skill-based) the way Pronote does: a single `evaluation` resource
        can carry either a numeric `mark` or a set of skill levels,
        depending on the school's grading system, so both are surfaced
        here under one unified list.
        """
        items: list[dict] = []
        for evaluation_service in self._evaluations:
            subject = evaluation_service.get("subject") or {}
            for evaluation in evaluation_service.get("evaluations") or []:
                results = evaluation.get("evaluationResults") or []
                mark = None
                skills = []
                for result in results:
                    if result.get("nonEvaluated") is not True and isinstance(
                        result.get("value"), (int, float)
                    ):
                        mark = float(result["value"])
                    for skill_result in result.get("subSkillsEvaluationResults") or []:
                        level = skill_result.get("level")
                        skill = (skill_result.get("subSkill") or {}).get("shortLabel")
                        if level or skill:
                            skills.append({"skill": skill, "level": level})
                items.append(
                    {
                        "id": evaluation.get("id"),
                        "subject": subject.get("label"),
                        "subject_color": subject.get("color"),
                        "title": evaluation.get("title") or evaluation.get("topic"),
                        "date": evaluation.get("dateTime"),
                        "mark": mark,
                        "scale": evaluation.get("scale"),
                        "coefficient": evaluation.get("coefficient"),
                        "class_average": evaluation.get("average"),
                        "skills": skills,
                    }
                )
        return items
