from datetime import date

from freezegun import freeze_time

from custom_components.skolengo.coordinator import (
    _classify_lesson_change,
    _compute_next_alarm,
    _find_student_info,
    _is_lesson_addition_genuine,
    _lesson_snapshot,
)
from custom_components.skolengo.const import (
    EVENT_TYPE_LESSON_CANCELED,
    EVENT_TYPE_LESSON_MODIFIED,
)


# --- _lesson_snapshot ------------------------------------------------------


def test_lesson_snapshot_extracts_the_tracked_fields():
    lesson = {
        "canceled": False,
        "startDateTime": "2026-09-10T08:00:00+00:00",
        "endDateTime": "2026-09-10T09:00:00+00:00",
        "location": "B204",
        "subject": {"label": "Mathématiques"},
        "teachers": [
            {"firstName": "Jean", "lastName": "Dupont"},
            {"firstName": "Alice", "lastName": "Martin"},
        ],
    }

    snapshot = _lesson_snapshot(lesson)

    assert snapshot == {
        "canceled": False,
        "startDateTime": "2026-09-10T08:00:00+00:00",
        "endDateTime": "2026-09-10T09:00:00+00:00",
        "location": "B204",
        "subject": "Mathématiques",
        # Sorted so the snapshot doesn't spuriously differ if the API
        # ever returns the same teachers in a different order.
        "teachers": ["Alice Martin", "Jean Dupont"],
    }


def test_lesson_snapshot_falls_back_to_room_and_title():
    lesson = {"room": "A101", "title": "Permanence"}

    snapshot = _lesson_snapshot(lesson)

    assert snapshot["location"] == "A101"
    assert snapshot["subject"] == "Permanence"


def test_lesson_snapshot_coerces_canceled_to_bool():
    assert _lesson_snapshot({"canceled": None})["canceled"] is False
    assert _lesson_snapshot({"canceled": True})["canceled"] is True


def test_lesson_snapshot_is_the_same_regardless_of_teacher_order():
    lesson_a = {"teachers": [{"lastName": "Dupont"}, {"lastName": "Martin"}]}
    lesson_b = {"teachers": [{"lastName": "Martin"}, {"lastName": "Dupont"}]}

    assert _lesson_snapshot(lesson_a) == _lesson_snapshot(lesson_b)


# --- _find_student_info -----------------------------------------------------


def test_find_student_info_for_a_legal_representative_account():
    user_info = {
        "id": "parent-1",
        "students": [
            {"id": "student-1", "firstName": "Ewen"},
            {"id": "student-2", "firstName": "Lilwenn"},
        ],
    }

    assert _find_student_info(user_info, "student-2") == {
        "id": "student-2",
        "firstName": "Lilwenn",
    }


def test_find_student_info_for_a_direct_student_login():
    user_info = {"id": "student-1", "firstName": "Ewen"}

    assert _find_student_info(user_info, "student-1") == user_info


def test_find_student_info_returns_empty_dict_when_not_found():
    user_info = {"id": "parent-1", "students": [{"id": "student-1"}]}

    assert _find_student_info(user_info, "unknown-student") == {}


# --- _compute_next_alarm ----------------------------------------------------


def _lesson(start_iso, canceled=False):
    return {"startDateTime": start_iso, "canceled": canceled}


@freeze_time("2026-09-10T06:00:00+00:00")
def test_next_alarm_is_todays_first_lesson_minus_offset():
    lessons = [
        _lesson("2026-09-10T08:00:00+00:00"),
        _lesson("2026-09-10T10:00:00+00:00"),
    ]

    alarm = _compute_next_alarm(lessons, offset_minutes=30)

    assert alarm.isoformat() == "2026-09-10T07:30:00+00:00"


@freeze_time("2026-09-10T09:00:00+00:00")
def test_next_alarm_rolls_over_once_todays_alarm_has_passed():
    lessons = [
        _lesson("2026-09-10T08:00:00+00:00"),  # today, already passed
        _lesson("2026-09-11T08:00:00+00:00"),  # tomorrow
    ]

    alarm = _compute_next_alarm(lessons, offset_minutes=60)

    assert alarm.isoformat() == "2026-09-11T07:00:00+00:00"


@freeze_time("2026-09-10T06:00:00+00:00")
def test_next_alarm_ignores_canceled_lessons():
    lessons = [
        _lesson("2026-09-10T07:00:00+00:00", canceled=True),
        _lesson("2026-09-10T09:00:00+00:00"),
    ]

    alarm = _compute_next_alarm(lessons, offset_minutes=0)

    assert alarm.isoformat() == "2026-09-10T09:00:00+00:00"


@freeze_time("2026-09-10T06:00:00+00:00")
def test_next_alarm_is_none_without_upcoming_lessons():
    assert _compute_next_alarm([], offset_minutes=30) is None
    assert _compute_next_alarm([_lesson("2026-09-10T07:00:00+00:00", canceled=True)], 0) is None


# --- _classify_lesson_change ------------------------------------------------


def test_classify_lesson_change_returns_none_when_unchanged():
    snapshot = _lesson_snapshot({"startDateTime": "2026-09-10T08:00:00+00:00"})

    assert _classify_lesson_change(snapshot, snapshot) is None


def test_classify_lesson_change_detects_new_cancellation():
    previous = _lesson_snapshot({"canceled": False})
    snapshot = _lesson_snapshot({"canceled": True})

    assert _classify_lesson_change(previous, snapshot) == EVENT_TYPE_LESSON_CANCELED


def test_classify_lesson_change_detects_reschedule():
    previous = _lesson_snapshot({"startDateTime": "2026-09-10T08:00:00+00:00"})
    snapshot = _lesson_snapshot({"startDateTime": "2026-09-10T09:00:00+00:00"})

    assert _classify_lesson_change(previous, snapshot) == EVENT_TYPE_LESSON_MODIFIED


def test_classify_lesson_change_treats_uncancel_as_modified():
    # Reinstating a canceled lesson is a real change worth notifying about,
    # just not the `lesson_canceled` type.
    previous = _lesson_snapshot({"canceled": True})
    snapshot = _lesson_snapshot({"canceled": False})

    assert _classify_lesson_change(previous, snapshot) == EVENT_TYPE_LESSON_MODIFIED


# --- _is_lesson_addition_genuine ---------------------------------------------


def test_addition_is_not_genuine_without_a_previous_window():
    lesson = {"startDateTime": "2026-09-10T08:00:00+00:00"}

    assert _is_lesson_addition_genuine(lesson, None) is False


def test_addition_is_not_genuine_when_beyond_the_previous_window():
    # This is the rolling-window case: AGENDA_DAYS_FUTURE moved forward by
    # a day, so this lesson is merely coming into view for the first time.
    lesson = {"startDateTime": "2026-09-26T08:00:00+00:00"}

    assert _is_lesson_addition_genuine(lesson, date(2026, 9, 25)) is False


def test_addition_is_genuine_when_inside_the_previous_window():
    # The lesson's date was already visible in the previous fetch's
    # window, yet the lesson itself wasn't returned -- a real addition
    # (e.g. a make-up lesson slotted into an already-visible day).
    lesson = {"startDateTime": "2026-09-20T08:00:00+00:00"}

    assert _is_lesson_addition_genuine(lesson, date(2026, 9, 25)) is True


def test_addition_is_not_genuine_without_a_parseable_date():
    assert _is_lesson_addition_genuine({}, date(2026, 9, 25)) is False
