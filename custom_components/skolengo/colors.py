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
