"""Restoration pack rules.

`is_emergency(text)`: damage that is still active, or a structural or sewage hazard.
`classify()`: a reply that promises coverage, quotes a cost or timescale, or judges
the property safe is raised to high and refused; a person follows up instead.
"""

from __future__ import annotations

import re
from typing import Any

_WATER = re.compile(r"\b(water|flood\w*|leak\w*|pipe|burst)\b", re.I)
_ACTIVE = re.compile(
    r"\b(still (coming|flowing|pouring|running|leaking|flooding|rising)|"
    r"can'?t (stop|turn (it|the water) off)|cannot (stop|turn)|"
    r"pouring (in|through)|coming through the ceiling)\b",
    re.I,
)
_FIRE = re.compile(r"\b(fire|smoke|flames?|burning)\b", re.I)
_FIRE_NOW = re.compile(r"\b(still|right now|now|spreading|can smell smoke)\b", re.I)
_COLLAPSE = re.compile(
    r"\b(ceiling|roof|wall|floor)\b.{0,30}"
    r"\b(collaps\w*|coming down|caving|sagging badly|falling)\b",
    re.I,
)
_SEWAGE = re.compile(r"\b(sewage|sewer|effluent|waste water backing up)\b", re.I)

_PROMISE = re.compile(
    r"\b(insurer|insurance|policy)\b.{0,40}"
    r"\b(will|should|definitely|always|usually) (cover|pay|accept)\b"
    r"|\b(covered by|fully covered|you're covered|you are covered)\b"
    r"|\b(£|\$|€)\s?\d|\b\d+\s?(pounds|dollars|euros)\b|\bcost (you|around|about|roughly)\b"
    r"|\b(safe to (stay|sleep|live)|perfectly safe|no need to worry)\b"
    r"|\b(dry (out )?in|take (about |around )?\d+ (days|weeks))\b",
    re.I,
)


def is_emergency(text: str) -> bool:
    if _WATER.search(text) and _ACTIVE.search(text):
        return True
    if _FIRE.search(text) and _FIRE_NOW.search(text):
        return True
    return bool(_COLLAPSE.search(text) or _SEWAGE.search(text))


def classify(kind: str, params: dict[str, Any], ctx: Any) -> str | None:
    if kind == "reply" and _PROMISE.search(str(params.get("text", ""))):
        return "high"
    return None
