"""The approval gate: one pure function that decides what happens to a proposal.

    decide(kind, params, ctx) -> Decision(risk, state, reason)

Order of authority, highest first:
1. Core rules. They can refuse or raise. No pack and no tenant can lower them.
2. The pack's `classify` hook. It may raise, or lower to the kind's floor.
3. Tenant overrides. They may lower, only within [floor, default], never below the floor.

The function takes plain values and touches no database, so it is tested as a
table (see packages/core/tests/test_gate.py) and reads like policy.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from novaxis_core.actions import ACTIONS, RISK_ORDER, Risk, params_valid

State = Literal["auto_approved", "awaiting", "rejected"]

# When a person must look before anything else happens. Matched on the customer's latest
# message and on the proposal's own text. A parent mentioning their child is ordinary (a
# family dentist hears it all day); what needs a person is a child who seems to be the one
# writing, a child left alone, or harm, threats, abuse or weapons.
_CHILD = r"(son|daughter|child|children|kid|kids|boy|girl|baby|toddler)"
_ALONE = r"(home alone|alone|on (his|her|their) own|by (him|her|them)sel(f|ves)|unsupervised)"
SAFEGUARDING = re.compile(
    r"\b("
    # The writer says they are a child: "I'm 13", "i am 14 years old", "I'm in year 8".
    r"(i'?m|i am) (only )?([5-9]|1[0-5])( ?(years?|yrs?)( old)?| ?y/?o)?\b"
    r"(?! (minutes|mins|hours|miles))|"
    r"(i'?m|i am) in year [1-9]\b|"
    # A child left alone.
    r""
    + _CHILD
    + r"\b[^.!?]{0,60}\b"
    + _ALONE
    + r"|"
    + _ALONE
    + r"\b[^.!?]{0,30}\b(my|the|our) "
    + _CHILD
    + r"|"
    # Harm, threats, abuse, weapons.
    r"kill (myself|him|her|them|you)|suicid\w*|self[- ]harm\w*|hurt (myself|him|her|them)|"
    r"threaten\w* (me|us|him|her|them)|threaten\w* to (kill|hurt|harm|attack)|"
    r"abus(e|ed|ing|ive)\b|assault\w*|weapon\w*|"
    r"(with|has|had|got|holding|carrying|bring|brought) an? (knife|gun|blade)"
    r")",
    re.IGNORECASE,
)

# Packs return a risk word or None. Typed loosely so packs need not import the gate.
PackRule = Callable[[str, dict[str, Any], Any], str | None]


@dataclass(frozen=True)
class GateContext:
    """Everything the gate may look at. Built by the caller from rows."""

    tenant_settings: dict[str, Any] = field(default_factory=dict)
    contact_consent: dict[str, Any] = field(default_factory=dict)
    latest_inbound_text: str = ""
    conversation_channel: str = ""
    pack_rule: PackRule | None = None


@dataclass(frozen=True)
class Decision:
    risk: Risk
    state: State
    reason: str

    @property
    def refused(self) -> bool:
        return self.state == "rejected"


_STATE: dict[Risk, State] = {"low": "auto_approved", "medium": "awaiting", "high": "rejected"}


def _state_for(risk: Risk) -> State:
    return _STATE[risk]


def _max(a: Risk, b: Risk) -> Risk:
    return a if RISK_ORDER[a] >= RISK_ORDER[b] else b


def _core_rules(
    kind: str, params: dict[str, Any], ctx: GateContext
) -> tuple[Risk | None, str | None]:
    """Return (forced_risk, reason) or (None, None). Forced risk can only raise."""
    sends = kind in {
        "reply",
        "handoff_notice",
        "ask_intake_question",
        "send_reminder",
        "outbound_first_contact",
        "confirm_appointment",
    }
    if sends and ctx.contact_consent.get("status") == "opted_out":
        return "high", "contact has opted out; no message may be sent"
    if kind == "outbound_first_contact":
        return "high", "first contact without a prior message is never automatic"
    if kind == "collect_payment":
        return "high", "payments are never automatic"
    text = " ".join(str(v) for v in params.values() if isinstance(v, str))
    if kind not in {"hand_to_human", "escalate_emergency", "handoff_notice"} and (
        SAFEGUARDING.search(ctx.latest_inbound_text) or SAFEGUARDING.search(text)
    ):
        return "high", "safeguarding: a person must review this conversation"
    return None, None


def _as_risk(word: str) -> Risk:
    if word == "low":
        return "low"
    if word == "medium":
        return "medium"
    return "high"


def _tenant_override(kind: str, ctx: GateContext) -> Risk | None:
    raw = (ctx.tenant_settings.get("risk_overrides") or {}).get(kind)
    return _as_risk(raw) if raw in RISK_ORDER else None


def _service_auto_confirm(params: dict[str, Any], ctx: GateContext) -> bool:
    code = params.get("service_code")
    for s in ctx.tenant_settings.get("services") or []:
        if s.get("code") == code:
            return bool(s.get("auto_confirm"))
    return False


def decide(kind: str, params: dict[str, Any], ctx: GateContext) -> Decision:
    if kind not in ACTIONS:
        return Decision("high", "rejected", f"unknown action kind {kind!r}")
    bad = params_valid(kind, params)
    if bad:
        return Decision("high", "rejected", bad)
    spec = ACTIONS[kind]

    forced, why = _core_rules(kind, params, ctx)
    if forced is not None:
        return Decision(forced, _state_for(forced), why or "core rule")

    risk: Risk = spec.default_risk
    reason = "default"

    if ctx.pack_rule is not None:
        raw = ctx.pack_rule(kind, params, ctx)
        if raw in RISK_ORDER:
            pack_risk = _as_risk(raw)
            lowered = RISK_ORDER[pack_risk] < RISK_ORDER[risk]
            if lowered and RISK_ORDER[pack_risk] < RISK_ORDER[spec.floor]:
                pack_risk = spec.floor
            risk, reason = pack_risk, "pack rule"

    override = _tenant_override(kind, ctx)
    if override is not None and RISK_ORDER[override] < RISK_ORDER[risk]:
        if RISK_ORDER[override] >= RISK_ORDER[spec.floor]:
            risk, reason = override, "tenant override"
        else:
            reason = f"tenant override below floor ignored (floor {spec.floor})"
    elif override is not None and RISK_ORDER[override] > RISK_ORDER[risk]:
        risk, reason = override, "tenant override (raised)"

    if kind == "confirm_appointment" and risk == "medium" and _service_auto_confirm(params, ctx):
        risk, reason = "low", "service has auto_confirm enabled"

    if kind == "quote_price" and risk == "medium" and not ctx.tenant_settings.get("price_list"):
        risk, reason = "high", "no tenant price list; prices are never invented"

    return Decision(risk, _state_for(risk), reason)


def max_risk(a: Risk, b: Risk) -> Risk:
    return _max(a, b)
