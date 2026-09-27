"""Phone numbers and email addresses in one canonical form, so the same number typed two
ways is recognised as the same number: when matching customers (contacts.py) and when a
business's SMS number or inbound address decides which business a message belongs to
(tenant_settings.py, routing.py)."""

from __future__ import annotations

import re

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_phone(raw: str) -> str | None:
    """E.164 for the numbers a UK business sees: 07700 900123, +44 7700 900123, 447700900123.
    Anything else with a leading + is kept as typed digits. Returns None if it is not a phone."""
    s = raw.strip().replace("(0)", "")  # "+44 (0)7700 ..." drops the trunk zero
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        out = "+" + digits
    elif digits.startswith("44"):
        out = "+" + digits
    elif digits.startswith("0") and len(digits) == 11:
        out = "+44" + digits[1:]
    else:
        return None
    return out if 10 <= len(out) - 1 <= 15 else None


def normalize_email(raw: str) -> str | None:
    s = raw.strip().lower()
    return s if EMAIL.match(s) else None


def routing_phone(raw: str) -> str | None:
    """A business's own SMS number in E.164, or None if it is not one. Stricter than
    `normalize_phone`: this value decides which business receives a text."""
    s = normalize_phone(raw) or re.sub(r"[\s().-]", "", raw.strip())
    return s if E164.match(s) else None
