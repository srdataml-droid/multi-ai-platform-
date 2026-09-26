"""HVAC pack rules. Two hooks, both optional, both plain functions.

`is_emergency(text)` runs before the model on every inbound message.
`classify(kind, params, ctx)` runs inside the gate after core rules.
"""

from __future__ import annotations

import re
from typing import Any

_VULNERABLE = re.compile(
    r"\b(baby|newborn|infant|elderly|pensioner|grandm\w*|grandf\w*|disab\w*|unwell|ill|sick|oxygen)\b",
    re.I,
)
_NO_HEAT = re.compile(
    r"\b(no (heating|heat|hot water)"
    r"|heating('s| is| has)? (gone|stopped|dead|off|broken)"
    r"|boiler('s| is)? (dead|off|not working))\b",
    re.I,
)


def is_emergency(text: str) -> bool:
    """No heating with a vulnerable occupant is treated as an emergency in winter or not;
    the on-call engineer decides how fast, but a person must see it now."""
    return bool(_NO_HEAT.search(text) and _VULNERABLE.search(text))


def classify(kind: str, params: dict[str, Any], ctx: Any) -> str | None:
    """A job for a vulnerable household should not wait in the approval queue behind others:
    raise it to medium with a reason rather than lower it, so a person sees it first."""
    if kind == "propose_appointment":
        notes = str(params.get("notes", "")).lower()
        if "vulnerable" in notes or "urgent" in notes:
            return "medium"
    return None
