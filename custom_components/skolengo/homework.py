"""Shared helpers for flattening Skolengo homework-assignment payloads.

Split out from `sensor.py` so `coordinator.py` can also serialize homework
(to detect new assignments and fire events) without a circular import.
"""
from __future__ import annotations


def flatten_homework(homework: dict) -> dict:
    """Flatten one `/homework-assignments` (or agenda-embedded) resource."""
    subject = homework.get("subject") or {}
    teacher = homework.get("teacher") or {}
    return {
        "id": homework.get("id"),
        "subject": subject.get("label"),
        "subject_color": subject.get("color"),
        "due_date": homework.get("dueDate") or homework.get("dueDateTime"),
        "done": bool(homework.get("done")),
        "title": homework.get("title"),
        "html": homework.get("html"),
        "teacher": f"{teacher.get('firstName', '')} {teacher.get('lastName', '')}".strip() or None,
    }
