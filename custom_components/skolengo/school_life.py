"""Flatten Skolengo's `/schooling-events-wrappers` payload (observations and
punishments of the "vie scolaire" screen) into plain dicts."""
from __future__ import annotations

from typing import Any


def _person_name(person: Any) -> str | None:
    if not isinstance(person, dict):
        return None
    parts = [person.get("title"), person.get("firstName"), person.get("lastName")]
    name = " ".join(str(p).strip() for p in parts if p)
    return name or None


def _first(source: dict, *keys: str) -> Any:
    for key in keys:
        if source.get(key):
            return source[key]
    return None


def flatten_observation(observation: dict) -> dict:
    reason = observation.get("reason") or {}
    return {
        "id": observation.get("id"),
        "date": observation.get("eventDateTime"),
        "tone": reason.get("tone"),
        "reason": reason.get("longLabel"),
        "issuer": _person_name(observation.get("issuer")),
        "comment": observation.get("comment"),
    }


def flatten_punishment(punishment: dict) -> dict:
    """Best-effort: punishments come in several shapes (deadline, point in
    time, time range) and none was available to inspect, so every plausible
    date field is read defensively."""
    reason = punishment.get("reason") or {}
    category = punishment.get("category") or {}
    return {
        "id": punishment.get("id"),
        "date": _first(
            punishment, "eventDateTime", "scheduledDateTime", "startDateTime", "dueDateTime"
        ),
        "end": punishment.get("endDateTime"),
        "due": punishment.get("dueDateTime"),
        "reason": reason.get("longLabel") or reason.get("label"),
        "category": category.get("longLabel") or category.get("label"),
        "issuer": _person_name(punishment.get("issuer")),
        "comment": punishment.get("comment"),
        "assigned_work": punishment.get("assignedWork"),
    }


def flatten_schooling_events(wrapper: dict | None) -> dict:
    """Return {"observations": [...], "punishments": [...], "positive": n,
    "negative": n, "punishments_to_realize": n | None}. Counters fall back
    to the list lengths when the API leaves them null."""
    wrapper = wrapper or {}
    observations = [flatten_observation(o) for o in wrapper.get("observations") or []]
    punishments = [flatten_punishment(p) for p in wrapper.get("punishments") or []]
    observations.sort(key=lambda o: o["date"] or "", reverse=True)
    punishments.sort(key=lambda p: p["date"] or "", reverse=True)

    positive = wrapper.get("positiveObservations")
    negative = wrapper.get("negativeObservations")
    if positive is None:
        positive = sum(1 for o in observations if o["tone"] == "POSITIVE")
    if negative is None:
        negative = sum(1 for o in observations if o["tone"] == "NEGATIVE")
    return {
        "observations": observations,
        "punishments": punishments,
        "positive": positive,
        "negative": negative,
        "punishments_to_realize": wrapper.get("punishmentsToRealize"),
    }
