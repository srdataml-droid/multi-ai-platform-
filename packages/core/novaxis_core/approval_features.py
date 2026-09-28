"""Model inputs for a proposal waiting for staff, computed one way for training and for
live scoring (same reason as features.py: one definition, or the model is quietly wrong).

The question the model answers: will staff approve this proposal *as written*? Approve is
a yes; reject and edit are a no (edit means it was not right as it stood).

No personal data and no message text: only what kind of action, why the gate held it,
how long the conversation is, the text's length and whether it mentions money or a time,
when it was proposed, and how often this business approved this kind of action *before*
this proposal existed. Every input is known when the proposal is made, so the model never
learns from the decision it is predicting.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from novaxis_core.models import ActionProposal, Approval, Conversation, Message, Tenant

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NUMERIC = (
    "text_len",
    "conv_messages",
    "customer_messages",
    "hour",
    "prior_rate",
    "prior_decisions",
    "has_money",
    "has_time",
)
CATEGORICAL = ("kind", "origin", "gate_reason", "channel", "pack_id", "weekday")
DECISIONS = ("approve", "reject", "edit")

_MONEY = re.compile(
    r"£|\$|€|\b\d+(\.\d{2})?\s?(gbp|pounds?|quid)\b|\b(price|cost|costs|quote|fee|charge)\b",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}/\d{1,2}\b|"
    r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day)?\b|\b(today|tomorrow|morning|"
    r"afternoon|evening)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProposalInput:
    kind: str
    params: dict[str, Any]
    reason: str
    created_at: datetime
    channel: str
    pack_id: str
    conv_messages: int
    customer_messages: int
    prior_approved: int
    prior_decided: int
    timezone: str = "Europe/London"


def _text(params: dict[str, Any]) -> str:
    return " ".join(str(v) for v in params.values() if isinstance(v, str))


_ORIGINS = {
    "model proposal": "model",
    "reply": "reply",
    "intake complete": "intake",
    "emergency keyword": "emergency",
    "service area": "service_area",
}


def _origin(reason: str) -> str:
    """Who proposed it: `propose(..., origin)` stores "<origin>: <gate reason>"."""
    head = reason.split(":", 1)[0].strip().lower()
    if head == "workflow":
        return "workflow"
    return _ORIGINS.get(head, "other")


def _gate_reason(reason: str) -> str:
    low = reason.lower()
    if "tenant override" in low:
        return "tenant_override"
    if "pack rule" in low:
        return "pack_rule"
    if low.endswith("default"):
        return "default"
    return "other"


def features(p: ProposalInput) -> dict[str, Any]:
    text = _text(p.params)
    local = p.created_at.astimezone(ZoneInfo(p.timezone))
    return {
        "text_len": round(min(len(text), 1000) / 100, 2),
        "conv_messages": float(min(p.conv_messages, 50)),
        "customer_messages": float(min(p.customer_messages, 30)),
        "hour": float(local.hour),
        # Smoothed so a business with no history starts at "no idea" (0.5), not 0 or 1.
        "prior_rate": round((p.prior_approved + 1) / (p.prior_decided + 2), 4),
        "prior_decisions": float(min(p.prior_decided, 50)),
        "has_money": 1.0 if ("amount_minor" in p.params or _MONEY.search(text)) else 0.0,
        "has_time": 1.0 if ("new_window" in p.params or _TIME.search(text)) else 0.0,
        "kind": p.kind,
        "origin": _origin(p.reason),
        "gate_reason": _gate_reason(p.reason),
        "channel": p.channel or "none",
        "pack_id": p.pack_id,
        "weekday": WEEKDAYS[local.weekday()],
    }


def input_for(session: Session, tenant: Tenant, p: ActionProposal) -> ProposalInput:
    """The inputs for one proposal of `tenant`, counting only what existed when it was made."""
    conv = session.get(Conversation, p.conversation_id) if p.conversation_id else None
    counts: dict[str, int] = {}
    if conv is not None:
        counts = {
            str(d): int(n)
            for d, n in session.execute(
                select(Message.direction, func.count())
                .where(Message.conversation_id == conv.id, Message.created_at <= p.created_at)
                .group_by(Message.direction)
            ).all()
        }
    history = {
        str(d): int(n)
        for d, n in session.execute(
            select(Approval.decision, func.count())
            .join(ActionProposal, ActionProposal.id == Approval.proposal_id)
            .where(
                and_(
                    ActionProposal.tenant_id == tenant.id,
                    ActionProposal.kind == p.kind,
                    Approval.created_at < p.created_at,
                    Approval.decision.in_(DECISIONS),
                )
            )
            .group_by(Approval.decision)
        ).all()
    }
    return ProposalInput(
        kind=p.kind,
        params=p.params,
        reason=p.reason or "",
        created_at=p.created_at,
        channel=conv.channel if conv else "none",
        pack_id=tenant.pack_id,
        conv_messages=sum(counts.values()),
        customer_messages=counts.get("inbound", 0),
        prior_approved=history.get("approve", 0),
        prior_decided=sum(history.values()),
        timezone=str(tenant.settings.get("timezone") or "Europe/London"),
    )


@dataclass(frozen=True)
class LabelledRow:
    created_at: datetime
    features: dict[str, Any]
    approved: int


def labelled_rows(session: Session, tenant_ids: list[uuid.UUID] | None = None) -> list[LabelledRow]:
    """Every proposal staff decided, as training rows, oldest first. `session` is a service
    session (training reads across businesses); rows carry no identifiers or text."""
    stmt = select(Tenant)
    if tenant_ids is not None:
        stmt = stmt.where(Tenant.id.in_(tenant_ids))
    rows: list[LabelledRow] = []
    for tenant in session.scalars(stmt):
        decided = session.execute(
            select(ActionProposal, Approval.decision)
            .join(Approval, Approval.proposal_id == ActionProposal.id)
            .where(ActionProposal.tenant_id == tenant.id, Approval.decision.in_(DECISIONS))
            .order_by(ActionProposal.created_at)
        ).all()
        for p, decision in decided:
            x = features(input_for(session, tenant, p))
            rows.append(LabelledRow(p.created_at, x, int(decision == "approve")))
    rows.sort(key=lambda r: r.created_at)
    return rows
