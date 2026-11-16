from datetime import datetime, timezone

from custom_components.skolengo.timetable import select_upcoming_canceled

NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)


def lesson(lid, start, end, canceled=True):
    return {"id": lid, "startDateTime": start, "endDateTime": end, "canceled": canceled}


def test_keeps_only_canceled_lessons_not_over_sorted_by_start():
    lessons = [
        lesson("late", "2026-11-20T08:00:00Z", "2026-11-20T09:00:00Z"),
        lesson("past", "2026-11-16T08:00:00Z", "2026-11-16T09:00:00Z"),
        lesson("running", "2026-11-16T09:30:00Z", "2026-11-16T10:30:00Z"),
        lesson("normal", "2026-11-17T08:00:00Z", "2026-11-17T09:00:00Z", canceled=False),
        lesson("soon", "2026-11-17T13:00:00Z", "2026-11-17T14:00:00Z"),
    ]

    result = select_upcoming_canceled(lessons, NOW)

    assert [item["id"] for item in result] == ["running", "soon", "late"]


def test_ignores_lessons_without_a_start_date():
    assert select_upcoming_canceled([{"id": "x", "canceled": True}], NOW) == []
