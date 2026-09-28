"""The intake engine: what to ask next, and whether we are done.

The model phrases questions; this engine decides which one. It reads the pack's
ordered question list and the conversation's extracted fields. Validation is
plain: a phone is digits with a plus, a postcode matches a loose UK/US shape, a
choice must be one of the options. Anything invalid is treated as unanswered so
the next turn asks again.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from novaxis_core.packspec import IntakeQuestion

_PATTERNS = {
    "phone": re.compile(r"^\+?[\d\s()-]{7,20}$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "postcode": re.compile(r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$|^\d{5}(-\d{4})?$"),
}


@dataclass(frozen=True)
class IntakeStatus:
    complete: bool
    next_question: IntakeQuestion | None
    answered: dict[str, str]
    invalid: dict[str, str]


def _skipped(q: IntakeQuestion, answered: dict[str, str]) -> bool:
    return bool(q.skip_if) and all(answered.get(k) == v for k, v in q.skip_if.items())


def valid_answer(q: IntakeQuestion, value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    if q.type == "choice":
        return v.lower() in {c.lower() for c in q.choices}
    if q.type == "yesno":
        return v.lower() in {"yes", "no", "y", "n", "true", "false"}
    if q.type in _PATTERNS and not _PATTERNS[q.type].match(v):
        return False
    if q.pattern and not re.match(q.pattern, v):
        return False
    return True


def status(questions: list[IntakeQuestion], extracted: dict[str, Any]) -> IntakeStatus:
    answered: dict[str, str] = {}
    invalid: dict[str, str] = {}
    for q in questions:
        raw = extracted.get(q.key)
        if raw is None:
            continue
        if valid_answer(q, str(raw)):
            answered[q.key] = str(raw).strip()
        else:
            invalid[q.key] = str(raw)
    for q in questions:
        if q.key in answered or _skipped(q, answered) or not q.required:
            continue
        return IntakeStatus(False, q, answered, invalid)
    return IntakeStatus(True, None, answered, invalid)


def prompt_block(questions: list[IntakeQuestion], extracted: dict[str, Any]) -> str:
    """What the model is told about intake this turn."""
    st = status(questions, extracted)
    lines = ["Intake keys and what you have so far:"]
    for q in questions:
        mark = (
            "answered"
            if q.key in st.answered
            else ("invalid, ask again" if q.key in st.invalid else "missing")
        )
        extra = f" (one of: {', '.join(q.choices)})" if q.choices else ""
        lines.append(f"- {q.key}{extra}: {mark}")
    if st.complete:
        lines.append("Intake is complete.")
    elif st.next_question:
        lines.append(f"Ask next, in your own words: {st.next_question.ask}")
        lines.append(
            f"Record the answer with extract_fields under the key '{st.next_question.key}'."
        )
    return "\n".join(lines)


def out_of_area(value: str | None, prefixes: list[str]) -> bool:
    """True when the tenant has a service area and the value is outside it."""
    if not prefixes or not value:
        return False
    v = value.replace(" ", "").upper()
    return not any(v.startswith(p.replace(" ", "").upper()) for p in prefixes)


EXTRACTION_PROMPT = (
    "You read what a customer just said and pull out the facts it states. Reply with a "
    "single JSON object and nothing else. Use only the keys listed. Leave a key out if the "
    "customer did not state it; never guess. For a key with a list of options, use exactly "
    "one of the options, or leave it out."
)


def extraction_block(questions: list[IntakeQuestion]) -> str:
    """The keys the extraction call may fill, in the pack's own words."""
    kinds = {"yesno": " Answer yes or no.", "phone": " A phone number.", "postcode": " A postcode."}
    lines = ["Keys:"]
    for q in questions:
        opts = f" One of: {', '.join(q.choices)}." if q.choices else ""
        lines.append(f"- {q.key}: {q.ask}{opts}{kinds.get(q.type, '')}")
    return "\n".join(lines)


def parse_extraction(text: str, questions: list[IntakeQuestion]) -> dict[str, str]:
    """The valid answers in a model's JSON reply. Anything else (prose, unknown keys,
    answers the engine would reject) is dropped, so a bad reply records nothing."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    by_key = {q.key: q for q in questions}
    out: dict[str, str] = {}
    for k, v in data.items():
        q = by_key.get(str(k))
        if q is None or v is None or isinstance(v, bool | dict | list):
            continue
        value = str(v).strip()
        if q.type == "choice":
            value = next((c for c in q.choices if c.lower() == value.lower()), value)
        if q.type == "yesno":
            yes_no = {"y": "yes", "true": "yes", "n": "no", "false": "no"}
            value = yes_no.get(value.lower(), value.lower())
        if valid_answer(q, value):
            out[q.key] = value
    return out
