"""Shared helper to normalize Skolengo `subject.color` values.

Skolengo returns this attribute inconsistently depending on the endpoint:
e.g. `#57006D` (with a leading `#`) from `/agendas`, but `57006D` (without
one) from `/evaluation-services` -- both for the very same subject.
Without normalizing, the bundled Lovelace cards' color validation (which
requires the `#`) silently falls back to the default color for one
endpoint's data but not the other, making the same subject appear in
different colors across cards.
"""
from __future__ import annotations

import re

_HEX_COLOR_RE = re.compile(r"^[0-9a-f]{3}([0-9a-f]{3})?$", re.IGNORECASE)


def normalize_color(color: str | None) -> str | None:
    if not color:
        return color
    color = color.strip()
    if color.startswith("#"):
        return color
    if _HEX_COLOR_RE.match(color):
        return f"#{color}"
    return color


# Skolengo's skill-evaluation results are graded on a fixed 4-level mastery
# scale (plus "not evaluated"), but the `/evaluation-services` endpoint
# returns the raw enum code (e.g. "SATISFACTORY_MASTERY") instead of the
# French label shown in Skolengo's own app -- translate it here so it
# doesn't leak into the UI as-is.
_MASTERY_LEVEL_LABELS = {
    "NOT_EVALUATED": "Aucune sélection",
    "INSUFFICIENT_MASTERY": "Maîtrise insuffisante",
    "FRAGILE_MASTERY": "Maîtrise fragile",
    "SATISFACTORY_MASTERY": "Maîtrise satisfaisante",
    "VERY_GOOD_MASTERY": "Très bonne maîtrise",
}


def normalize_mastery_level(level: str | None) -> str | None:
    """Translate a Skolengo skill-evaluation level to its French label.

    Unknown values (e.g. schools using a different, already human-readable
    grading vocabulary) are returned unchanged.
    """
    if not level:
        return level
    return _MASTERY_LEVEL_LABELS.get(level.strip(), level)
