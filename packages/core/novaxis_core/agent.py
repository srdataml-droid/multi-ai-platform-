"""The agent API's rules, for a business's own agent (e.g. one built with Hermes).

An external agent reads a conversation and *proposes* actions. Everything it proposes goes
through `propose()`, the same path and the same approval gate as the built-in assistant:
low risk runs, medium waits for staff, high is refused. It can never send, book or cancel
directly, and it can only propose the tools the business's pack gives the built-in model,
plus `reply`.

The platform keeps the safety parts to itself, whoever the agent is:
- the emergency pre-check still runs on every customer message (turn.py);
- the first reply to a customer always opens with the AI disclosure, added here;
- consent, safeguarding and the risk rules are the gate's, not the agent's.

What an agent sees is only what it needs: the conversation, the contact's name and consent,
the intake answers (sensitive ones withheld), bookings, and the business's facts. Not phone
numbers or email addresses: replies go out through the platform's own channels.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.gate import GateContext
from novaxis_core.models import (
    ActionProposal,
    AgentKey,
    Appointment,
    Contact,
    Conversation,
    Message,
    Tenant,
)
from novaxis_core.packspec import PackSpec

KEY_PREFIX = "nvx_agent_"
DUPLICATE_WINDOW = timedelta(minutes=10)
REPLY_TOOL: dict[str, Any] = {
    "name": "reply",
    "description": "Send this text to the customer in the conversation. Keep it brief and "
    "never promise a booking, a price or that anyone was alerted unless a proposal did it.",
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The message to send"}},
        "required": ["text"],
        "additionalProperties": False,
    },
}


class AgentError(ValueError):
    """The agent asked for something it may not do (HTTP 422)."""


# --- keys ------------------------------------------------------------------------------


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key(
    session: Session, tenant_id: uuid.UUID, name: str, created_by: uuid.UUID | None
) -> tuple[AgentKey, str]:
    """Returns (row, the key). The key is shown once; only its hash is stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = AgentKey(
        tenant_id=tenant_id,
        name=name.strip()[:80] or "agent",
        prefix=key[: len(KEY_PREFIX) + 6],
        key_hash=hash_key(key),
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row, key


def find_key(service: Session, key: str) -> AgentKey | None:
    """Service session: the key decides the tenant. Revoked keys do not exist."""
    if not key.startswith(KEY_PREFIX):
        return None
    row = service.scalar(select(AgentKey).where(AgentKey.key_hash == hash_key(key)))
    if row is None or row.revoked_at is not None:
        return None
    return row


# --- what the agent may use -------------------------------------------------------------


def allowed_tools(pack: PackSpec) -> list[dict[str, Any]]:
    return [REPLY_TOOL, *pack.tools]


def openai_tools(pack: PackSpec) -> list[dict[str, Any]]:
    """The same tools in the OpenAI function-calling format that Hermes models and most
    agent frameworks read [VERIFY your framework's format]."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in allowed_tools(pack)
    ]


# --- reading ----------------------------------------------------------------------------


def _open(conv: Conversation) -> bool:
    return conv.status in ("open", "waiting_customer")


def waiting(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    """Conversations where the customer spoke last and nobody has answered: the agent's
    to-do list. Conversations with a person (waiting_human) or closed are not listed."""
    out: list[dict[str, Any]] = []
    convs = session.scalars(
        select(Conversation)
        .where(Conversation.status.in_(["open", "waiting_customer"]))
        .order_by(Conversation.updated_at.desc())
        .limit(200)
    )
    for conv in convs:
        last = session.scalar(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        if last is None or last.direction != "inbound":
            continue
        out.append(
            {
                "conversation_id": str(conv.id),
                "channel": conv.channel,
                "status": conv.status,
                "last_message_at": last.created_at.isoformat(),
            }
        )
        if len(out) >= limit:
            break
    return out


def _intake(pack: PackSpec, plain: dict[str, Any]) -> dict[str, Any]:
    """The intake answers so far (sensitive ones withheld) and the next question to ask."""
    from novaxis_core.intake import status as intake_status

    answers = {
        k: ("(held by the business)" if k in pack.sensitive_keys else v) for k, v in plain.items()
    }
    if not pack.intake:
        return {"answers": answers, "complete": True, "next_question": None}
    st = intake_status(pack.intake, plain)
    nxt = st.next_question
    return {
        "answers": answers,
        "complete": st.complete,
        "next_question": {"key": nxt.key, "ask": nxt.ask, "type": nxt.type, "choices": nxt.choices}
        if nxt
        else None,
    }


def context(session: Session, tenant: Tenant, pack: PackSpec, conv: Conversation) -> dict[str, Any]:
    from novaxis_core.sensitive import decrypt_fields
    from novaxis_core.turn import tenant_facts

    contact = session.get(Contact, conv.contact_id)
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(50)
        )
    )[::-1]
    plain = decrypt_fields(conv.extracted, pack.sensitive_keys)
    appts = session.scalars(
        select(Appointment)
        .where(
            Appointment.contact_id == conv.contact_id,
            Appointment.status.in_(["held", "confirmed", "proposed"]),
        )
        .order_by(Appointment.starts_at)
    )
    pending = session.scalars(
        select(ActionProposal)
        .where(ActionProposal.conversation_id == conv.id, ActionProposal.state == "awaiting")
        .order_by(ActionProposal.created_at)
    )
    return {
        "conversation": {
            "id": str(conv.id),
            "channel": conv.channel,
            "status": conv.status,
            "summary": conv.summary,
            "agent_may_act": _open(conv),
        },
        "contact": {
            "name": contact.display_name if contact else None,
            "consent": (contact.consent or {}).get("status", "unknown") if contact else "unknown",
        },
        "messages": [
            {
                "id": str(m.id),
                "from": "customer"
                if m.direction == "inbound"
                else ("staff" if m.author == "human" else "assistant"),
                "text": m.body,
                "at": m.created_at.isoformat(),
                "attachments": len(m.media or []),
            }
            for m in messages
        ],
        "intake": _intake(pack, plain),
        "appointments": [
            {
                "appointment_id": str(a.id),
                "service_code": a.service_code,
                "starts_at": a.starts_at.isoformat(),
                "status": a.status,
            }
            for a in appts
        ],
        "awaiting_staff": [{"proposal_id": str(p.id), "kind": p.kind} for p in pending],
        "business": tenant_facts(tenant),
        "tools": [t["name"] for t in allowed_tools(pack)],
    }


# --- proposing ----------------------------------------------------------------------------


def gate_context(
    session: Session, tenant: Tenant, pack: PackSpec, conv: Conversation
) -> GateContext:
    """Built exactly as the worker turn builds it, so the gate treats the agent the same."""
    contact = session.get(Contact, conv.contact_id)
    last_inbound = session.scalar(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.direction == "inbound")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return GateContext(
        tenant_settings=tenant.settings,
        contact_consent=contact.consent if contact else {},
        latest_inbound_text=last_inbound.body if last_inbound else "",
        conversation_channel=conv.channel,
        pack_rule=pack.rule,
    )


def _first_reply(session: Session, conv: Conversation) -> bool:
    return (
        session.scalar(
            select(Message.id)
            .where(
                Message.conversation_id == conv.id,
                Message.direction == "outbound",
                Message.author == "worker",
            )
            .limit(1)
        )
        is None
    )


def agent_propose(
    session: Session,
    tenant: Tenant,
    pack: PackSpec,
    conv: Conversation,
    key: AgentKey,
    kind: str,
    params: dict[str, Any],
) -> tuple[ActionProposal, bool]:
    """Returns (proposal, created). An identical proposal from an agent in the last ten
    minutes is returned instead of a second one, so a retried request never sends a
    customer the same message twice."""
    from novaxis_core.turn import disclosure_for, propose

    names = {t["name"] for t in allowed_tools(pack)}
    if kind not in names:
        raise AgentError(f"{kind!r} is not one of this business's tools: {sorted(names)}")
    disclosure = disclosure_for(tenant) if kind == "reply" else ""
    text = str(params.get("text", ""))
    with_disclosure = {**params, "text": f"{disclosure}\n\n{text}"} if disclosure else params

    # A retry is recognised before anything else, even if the first attempt changed the
    # conversation (a hand-off) or had the disclosure added.
    since = datetime.now(UTC) - DUPLICATE_WINDOW
    for earlier in session.scalars(
        select(ActionProposal).where(
            ActionProposal.conversation_id == conv.id,
            ActionProposal.kind == kind,
            ActionProposal.reason.like("agent:%"),
            ActionProposal.created_at >= since,
        )
    ):
        if earlier.params in (params, with_disclosure):
            return earlier, False

    if not _open(conv):
        raise AgentError(f"conversation is {conv.status}; a person or nobody should act on it")
    if disclosure and _first_reply(session, conv) and not text.startswith(disclosure):
        params = with_disclosure

    p, _ = propose(
        session,
        tenant,
        conv,
        kind,
        params,
        gate_context(session, tenant, pack, conv),
        f"agent:{key.name}",
    )
    if kind == "reply" and p.state == "executed" and conv.status == "open":
        conv.status = "waiting_customer"
    conv.updated_at = datetime.now(UTC)
    session.flush()
    return p, True


def proposal_view(p: ActionProposal) -> dict[str, Any]:
    return {
        "proposal_id": str(p.id),
        "kind": p.kind,
        "state": p.state,
        "risk": p.risk,
        "reason": p.reason,
        "error": p.error,
        "result": p.result,
    }
