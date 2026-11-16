"""Helpers for picking lessons out of the timetable (agenda)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def select_upcoming_canceled(lessons: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Canceled lessons that are not over yet, soonest first.

    A lesson still counts while it is in progress (its end is in the future),
    so a lesson canceled for this very hour keeps showing until it would
    have ended. Lessons without a usable start date are ignored.
    """
    selected: list[tuple[datetime, dict[str, Any]]] = []
    for lesson in lessons:
        if not lesson.get("canceled"):
            continue
        start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
        if not start:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt_util.UTC)
        end = dt_util.parse_datetime(lesson.get("endDateTime") or "") or start
        if end.tzinfo is None:
            end = end.replace(tzinfo=dt_util.UTC)
        if end >= now:
            selected.append((start, lesson))
    selected.sort(key=lambda item: item[0])
    return [lesson for _, lesson in selected]
