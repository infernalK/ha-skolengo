"""Shared helpers for flattening Skolengo homework-assignment payloads.

Split out from `sensor.py` so `coordinator.py` can also serialize homework
(to detect new assignments and fire events) without a circular import.
"""
from __future__ import annotations

from datetime import date, datetime

from homeassistant.util import dt as dt_util

from .colors import normalize_color


def flatten_homework(homework: dict) -> dict:
    """Flatten one `/homework-assignments` (or agenda-embedded) resource."""
    subject = homework.get("subject") or {}
    teacher = homework.get("teacher") or {}
    return {
        "id": homework.get("id"),
        "subject": subject.get("label"),
        "subject_color": normalize_color(subject.get("color")),
        "due_date": homework.get("dueDate") or homework.get("dueDateTime"),
        "done": bool(homework.get("done")),
        "title": homework.get("title"),
        "html": homework.get("html"),
        "teacher": f"{teacher.get('firstName', '')} {teacher.get('lastName', '')}".strip() or None,
    }


def _due_key(homework: dict) -> str:
    return homework.get("dueDate") or homework.get("dueDateTime") or ""


def _due_day(homework: dict) -> date | None:
    """Due day of a raw homework resource, in Home Assistant's timezone."""
    raw = _due_key(homework)
    if not raw:
        return None
    parsed = dt_util.parse_datetime(raw)
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return dt_util.as_local(parsed).date()
    return dt_util.parse_date(raw)


def select_homework_attributes(
    homework: list[dict], today: date | None = None, max_past: int = 30
) -> tuple[list[dict], list[dict]]:
    """Return the raw (not done, done) homework lists to expose on the sensor.

    Every assignment due today or later is kept (there are only a few), while
    the past ones are capped to the `max_past` most recent. Capping the whole
    list by ascending due date would fill it with months-old, never-ticked
    homework and push the upcoming ones out. The not-done list is sorted by
    ascending due date, the done list most recent first.
    """
    if today is None:
        today = dt_util.now().date()

    def pick(items: list[dict]) -> list[dict]:
        ordered = sorted(items, key=_due_key)
        upcoming, past = [], []
        for hw in ordered:
            day = _due_day(hw)
            # No parsable due date: treat as upcoming so it is never dropped.
            (past if day is not None and day < today else upcoming).append(hw)
        return (past[-max_past:] if max_past else []) + upcoming

    not_done = pick([hw for hw in homework if not hw.get("done")])
    done = list(reversed(pick([hw for hw in homework if hw.get("done")])))
    return not_done, done
