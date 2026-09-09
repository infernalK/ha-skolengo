from freezegun import freeze_time

from custom_components.skolengo.coordinator import (
    _compute_next_alarm,
    _find_student_info,
    _lesson_snapshot,
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
