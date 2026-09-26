"""Dental pack rules.

`is_emergency(text)`: swelling with breathing or swallowing trouble, bleeding that will not
stop, facial trauma. `classify()`: any reply that reads like clinical advice is raised to
high, so it is refused and a person follows up; the practice, not the assistant, advises.
"""

from __future__ import annotations

import re
from typing import Any

_SWELLING = re.compile(r"\b(swell\w*|swollen)\b", re.I)
_AIRWAY = re.compile(r"\b(breath\w*|swallow\w*|throat|eye|airway)\b", re.I)
_BLEED = re.compile(r"\bbleed\w*\b", re.I)
_BLEED_BAD = re.compile(r"\b(won'?t stop|will not stop|hours|heavy|uncontroll\w*|pouring)\b", re.I)
_TRAUMA = re.compile(
    r"\b(knocked out|knocked-out|fell|accident|hit in the (face|mouth)|broken jaw)\b", re.I
)

_ADVICE = re.compile(
    r"\b(take|try|use|apply|rinse with|swallow)\b.{0,40}\b(ibuprofen|paracetamol|painkiller\w*|"
    r"antibiotic\w*|aspirin|codeine|clove oil|salt ?water|mouthwash|gel|tablet\w*|mg)\b"
    r"|\b(you should|i recommend|i'd suggest|i suggest)\b.{0,60}\b(take|rinse|apply|use)\b"
    r"|\b(it'?s|that'?s|this is|sounds) (probably |likely |just )?(nothing serious|not serious|"
    r"an abscess|an infection|a cavity|decay|gum disease)\b",
    re.I,
)


def is_emergency(text: str) -> bool:
    if _SWELLING.search(text) and _AIRWAY.search(text):
        return True
    if _BLEED.search(text) and _BLEED_BAD.search(text):
        return True
    return bool(_TRAUMA.search(text) and re.search(r"\btooth|teeth|jaw\b", text, re.I))


def classify(kind: str, params: dict[str, Any], ctx: Any) -> str | None:
    if kind == "reply" and _ADVICE.search(str(params.get("text", ""))):
        return "high"
    return None
