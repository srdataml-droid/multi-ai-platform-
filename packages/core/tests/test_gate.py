"""The gate as a table. Each row: kind, params, context tweaks, expected (risk, state)."""

from __future__ import annotations

from typing import Any

import pytest

from novaxis_core.actions import ACTIONS
from novaxis_core.executors import registered_kinds
from novaxis_core.gate import GateContext, decide

OK_SERVICES = [{"code": "repair", "name": "Repair", "duration_minutes": 60, "auto_confirm": False}]
AUTO_SERVICES = [
    {"code": "checkup", "name": "Check-up", "duration_minutes": 20, "auto_confirm": True}
]


def pack_lowers(kind: str, params: dict[str, Any], ctx: GateContext) -> str | None:
    return "low"


def pack_raises(kind: str, params: dict[str, Any], ctx: GateContext) -> str | None:
    return "high" if kind == "reply" and "advice" in params.get("text", "") else None


CASES: list[tuple[str, str, dict[str, Any], dict[str, Any], tuple[str, str]]] = [
    # ---- defaults per kind ----
    ("reply default", "reply", {"text": "hi"}, {}, ("low", "auto_approved")),
    (
        "intake question default",
        "ask_intake_question",
        {"question_key": "name", "text": "Name?"},
        {},
        ("low", "auto_approved"),
    ),
    ("extract default", "extract_fields", {"fields": {"a": "b"}}, {}, ("low", "auto_approved")),
    (
        "propose default",
        "propose_appointment",
        {"service_code": "repair"},
        {},
        ("medium", "awaiting"),
    ),
    ("confirm default", "confirm_appointment", {"appointment_id": "x"}, {}, ("medium", "awaiting")),
    (
        "reschedule default",
        "reschedule_appointment",
        {"appointment_id": "x", "new_window": "tue"},
        {},
        ("medium", "awaiting"),
    ),
    ("cancel default", "cancel_appointment", {"appointment_id": "x"}, {}, ("medium", "awaiting")),
    (
        "reminder default",
        "send_reminder",
        {"appointment_id": "x", "text": "Reminder"},
        {},
        ("low", "auto_approved"),
    ),
    ("escalate default", "escalate_emergency", {"summary": "gas"}, {}, ("low", "auto_approved")),
    ("hand default", "hand_to_human", {"reason": "asked"}, {}, ("low", "auto_approved")),
    (
        "first contact default",
        "outbound_first_contact",
        {"to": "+1", "channel": "twilio_sms", "text": "hi"},
        {},
        ("high", "rejected"),
    ),
    (
        "vendor write default",
        "write_to_vendor_system",
        {"provider": "x", "operation": "create"},
        {},
        ("medium", "awaiting"),
    ),
    (
        "payment default",
        "collect_payment",
        {"amount_minor": 100, "currency": "GBP"},
        {},
        ("high", "rejected"),
    ),
    (
        "quote default no list",
        "quote_price",
        {"service_code": "r", "amount_minor": 100, "currency": "GBP"},
        {},
        ("high", "rejected"),
    ),
    ("verify claim default", "verify_claim", {"text": "booked"}, {}, ("medium", "awaiting")),
    # ---- invalid input ----
    ("unknown kind", "teleport", {}, {}, ("high", "rejected")),
    ("bad params", "reply", {"nope": 1}, {}, ("high", "rejected")),
    ("empty reply", "reply", {"text": ""}, {}, ("high", "rejected")),
    ("extra param", "hand_to_human", {"reason": "x", "extra": 1}, {}, ("high", "rejected")),
    # ---- core rules: opted out ----
    (
        "opted out reply",
        "reply",
        {"text": "hi"},
        {"consent": {"status": "opted_out"}},
        ("high", "rejected"),
    ),
    (
        "opted out reminder",
        "send_reminder",
        {"appointment_id": "x", "text": "r"},
        {"consent": {"status": "opted_out"}},
        ("high", "rejected"),
    ),
    (
        "opted out confirm",
        "confirm_appointment",
        {"appointment_id": "x"},
        {"consent": {"status": "opted_out"}},
        ("high", "rejected"),
    ),
    (
        "opted out extract still fine",
        "extract_fields",
        {"fields": {"a": "b"}},
        {"consent": {"status": "opted_out"}},
        ("low", "auto_approved"),
    ),
    (
        "opted out hand off still fine",
        "hand_to_human",
        {"reason": "x"},
        {"consent": {"status": "opted_out"}},
        ("low", "auto_approved"),
    ),
    # ---- core rules: safeguarding ----
    (
        "minor in message",
        "reply",
        {"text": "sure"},
        {"inbound": "it's for my daughter, she's 9 years old"},
        ("high", "rejected"),
    ),
    (
        "threat in message",
        "propose_appointment",
        {"service_code": "repair"},
        {"inbound": "I'll bring a knife if you don't come"},
        ("high", "rejected"),
    ),
    (
        "self harm in message",
        "reply",
        {"text": "ok"},
        {"inbound": "honestly I want to kill myself"},
        ("high", "rejected"),
    ),
    (
        "safeguarding in params",
        "reply",
        {"text": "your son can come alone"},
        {},
        ("high", "rejected"),
    ),
    (
        "safeguarding does not block hand off",
        "hand_to_human",
        {"reason": "child"},
        {"inbound": "my son is hurt"},
        ("low", "auto_approved"),
    ),
    (
        "safeguarding does not block escalation",
        "escalate_emergency",
        {"summary": "child in danger"},
        {"inbound": "my child"},
        ("low", "auto_approved"),
    ),
    (
        "years old alone is enough",
        "reply",
        {"text": "ok"},
        {"inbound": "my kid is 12 years old"},
        ("high", "rejected"),
    ),
    # ---- tenant overrides ----
    (
        "tenant lowers propose to low",
        "propose_appointment",
        {"service_code": "repair"},
        {"overrides": {"propose_appointment": "low"}},
        ("low", "auto_approved"),
    ),
    (
        "tenant lowers confirm to low",
        "confirm_appointment",
        {"appointment_id": "x"},
        {"overrides": {"confirm_appointment": "low"}},
        ("low", "auto_approved"),
    ),
    (
        "tenant cannot lower cancel below floor",
        "cancel_appointment",
        {"appointment_id": "x"},
        {"overrides": {"cancel_appointment": "low"}},
        ("medium", "awaiting"),
    ),
    (
        "tenant cannot lower first contact",
        "outbound_first_contact",
        {"to": "+1", "channel": "twilio_sms", "text": "hi"},
        {"overrides": {"outbound_first_contact": "low"}},
        ("high", "rejected"),
    ),
    (
        "tenant cannot lower payment",
        "collect_payment",
        {"amount_minor": 1, "currency": "GBP"},
        {"overrides": {"collect_payment": "low"}},
        ("high", "rejected"),
    ),
    (
        "tenant raises reply to medium",
        "reply",
        {"text": "hi"},
        {"overrides": {"reply": "medium"}},
        ("medium", "awaiting"),
    ),
    (
        "tenant raises extract to high",
        "extract_fields",
        {"fields": {"a": "b"}},
        {"overrides": {"extract_fields": "high"}},
        ("high", "rejected"),
    ),
    (
        "tenant override ignored on unknown risk word",
        "propose_appointment",
        {"service_code": "repair"},
        {"overrides": {"propose_appointment": "none"}},
        ("medium", "awaiting"),
    ),
    (
        "tenant override cannot beat opt-out",
        "reply",
        {"text": "hi"},
        {"overrides": {"reply": "low"}, "consent": {"status": "opted_out"}},
        ("high", "rejected"),
    ),
    (
        "tenant override cannot beat safeguarding",
        "reply",
        {"text": "hi"},
        {"overrides": {"reply": "low"}, "inbound": "my son"},
        ("high", "rejected"),
    ),
    # ---- service auto-confirm ----
    (
        "auto confirm service lowers confirm",
        "confirm_appointment",
        {"appointment_id": "x", "service_code": "checkup"},
        {"services": AUTO_SERVICES},
        ("low", "auto_approved"),
    ),
    (
        "non auto service keeps confirm medium",
        "confirm_appointment",
        {"appointment_id": "x", "service_code": "repair"},
        {"services": OK_SERVICES},
        ("medium", "awaiting"),
    ),
    (
        "unknown service keeps confirm medium",
        "confirm_appointment",
        {"appointment_id": "x", "service_code": "zzz"},
        {"services": AUTO_SERVICES},
        ("medium", "awaiting"),
    ),
    # ---- price list ----
    (
        "quote with price list and override is medium",
        "quote_price",
        {"service_code": "r", "amount_minor": 100, "currency": "GBP"},
        {"overrides": {"quote_price": "medium"}, "price_list": {"r": 100}},
        ("medium", "awaiting"),
    ),
    (
        "quote override without price list stays high",
        "quote_price",
        {"service_code": "r", "amount_minor": 100, "currency": "GBP"},
        {"overrides": {"quote_price": "medium"}},
        ("high", "rejected"),
    ),
    (
        "quote cannot go low even with list",
        "quote_price",
        {"service_code": "r", "amount_minor": 100, "currency": "GBP"},
        {"overrides": {"quote_price": "low"}, "price_list": {"r": 100}},
        ("high", "rejected"),
    ),
    # ---- pack rules ----
    (
        "pack lowers propose to low",
        "propose_appointment",
        {"service_code": "repair"},
        {"rule": pack_lowers},
        ("low", "auto_approved"),
    ),
    (
        "pack cannot lower cancel below floor",
        "cancel_appointment",
        {"appointment_id": "x"},
        {"rule": pack_lowers},
        ("medium", "awaiting"),
    ),
    (
        "pack cannot lower payment",
        "collect_payment",
        {"amount_minor": 1, "currency": "GBP"},
        {"rule": pack_lowers},
        ("high", "rejected"),
    ),
    (
        "pack raises reply with advice",
        "reply",
        {"text": "my advice is take two"},
        {"rule": pack_raises},
        ("high", "rejected"),
    ),
    (
        "pack leaves other replies alone",
        "reply",
        {"text": "hello"},
        {"rule": pack_raises},
        ("low", "auto_approved"),
    ),
    (
        "tenant cannot undo pack raise below floor? (reply floor low so it can)",
        "reply",
        {"text": "my advice"},
        {"rule": pack_raises, "overrides": {"reply": "low"}},
        ("low", "auto_approved"),
    ),
]


def _ctx(tweaks: dict[str, Any]) -> GateContext:
    settings: dict[str, Any] = {}
    if "overrides" in tweaks:
        settings["risk_overrides"] = tweaks["overrides"]
    if "services" in tweaks:
        settings["services"] = tweaks["services"]
    if "price_list" in tweaks:
        settings["price_list"] = tweaks["price_list"]
    return GateContext(
        tenant_settings=settings,
        contact_consent=tweaks.get("consent", {}),
        latest_inbound_text=tweaks.get("inbound", ""),
        pack_rule=tweaks.get("rule"),
    )


@pytest.mark.parametrize("name,kind,params,tweaks,expected", CASES, ids=[c[0] for c in CASES])
def test_gate_table(
    name: str, kind: str, params: dict[str, Any], tweaks: dict[str, Any], expected: tuple[str, str]
) -> None:
    d = decide(kind, params, _ctx(tweaks))
    assert (d.risk, d.state) == expected, d.reason


def test_table_has_at_least_forty_rows() -> None:
    assert len(CASES) >= 40


def test_every_action_kind_has_an_executor() -> None:
    assert set(ACTIONS) <= registered_kinds()


def test_every_kind_is_covered_by_the_table() -> None:
    covered = {c[1] for c in CASES}
    assert set(ACTIONS) <= covered
