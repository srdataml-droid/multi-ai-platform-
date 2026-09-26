"""One worker turn: rows in, one LLM call, rows out.

Context is built from the database every time, never from prior model output
alone, so a turn is reproducible from rows. The model gets the pack's stable
system prompt (cached), the tenant's facts, a stored summary if there is one, and
the last N messages as plain alternating turns. Its text becomes the reply; its
tool calls become proposals. Chunk 4 adds the gate; here every proposal is stored
at low risk and nothing but the reply is executed.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.llm import LLMClient, LLMResult, ToolCall
from novaxis_core.models import (
    ActionProposal,
    AuditLog,
    Contact,
    Conversation,
    Message,
    Tenant,
    UsageEvent,
)
from novaxis_core.outbound import send_message
from novaxis_core.packspec import PackSpec
from novaxis_core.settings import get_settings

# Phrases that claim a side effect happened. If the model says one without the
# matching tool call, a human verifies before the customer relies on it.
BOOKING_CLAIMS = re.compile(
    r"\b(i have|i've|we have|we've|you're|you are)\s+(now\s+)?"
    r"(booked|scheduled|confirmed|reserved)\b"
    r"|\bbooked you in\b|\byour appointment is (booked|confirmed)\b",
    re.IGNORECASE,
)
CLAIM_TOOLS = {"propose_appointment", "confirm_appointment"}
SUMMARISE_PROMPT = (
    "Summarise this customer conversation in five short lines for a colleague: who, need, "
    "facts given, what was proposed, what is outstanding. No greetings."
)


@dataclass
class TurnResult:
    conversation_id: uuid.UUID
    reply_message_id: uuid.UUID | None
    proposal_ids: list[uuid.UUID] = field(default_factory=list)
    skipped_reason: str | None = None
    emergency: bool = False


def _audit(session: Session, tenant_id: uuid.UUID, event: str, **diff: object) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor="worker",
            event=event,
            diff={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in diff.items()},
        )
    )


def tenant_facts(tenant: Tenant) -> str:
    """The volatile half of the system prompt: what this business is."""
    s = tenant.settings
    lines = [f"Business name: {tenant.name}", f"Tone: {s.get('tone', 'friendly, brief')}"]
    hours = s.get("business_hours") or {}
    if hours:
        lines.append(
            "Opening hours: " + ", ".join(f"{d} {h['open']}-{h['close']}" for d, h in hours.items())
        )
    services = s.get("services") or []
    if services:
        lines.append(
            "Services (code: name, minutes): "
            + "; ".join(f"{x['code']}: {x['name']}, {x['duration_minutes']}" for x in services)
        )
    area = s.get("service_area") or []
    if area:
        lines.append("Service area prefixes: " + ", ".join(area))
    return "Business facts:\n" + "\n".join(lines)


def build_messages(history: list[Message]) -> list[dict[str, Any]]:
    """Alternating user/assistant text turns. Consecutive same-role messages merge."""
    out: list[dict[str, Any]] = []
    for m in history:
        role = "user" if m.direction == "inbound" else "assistant"
        body = m.body
        if m.direction == "outbound" and m.author == "human":
            body = f"[staff member]: {body}"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + body
        else:
            out.append({"role": role, "content": body})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(conversation opened)"})
    if out[-1]["role"] == "assistant":
        out.append({"role": "user", "content": "(no reply yet)"})
    return out


def _record_usage(
    session: Session, tenant: Tenant, conv_id: uuid.UUID, task: str, r: LLMResult
) -> None:
    session.add(
        UsageEvent(
            tenant_id=tenant.id,
            kind=f"llm.{task}",
            quantity=r.input_tokens + r.output_tokens,
            unit="tokens",
            model=r.model,
            meta={
                "conversation_id": str(conv_id),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cache_read_tokens": r.cache_read_tokens,
                "cache_write_tokens": r.cache_write_tokens,
                "latency_ms": r.latency_ms,
                "request_id": r.request_id,
            },
        )
    )


def _store_proposal(
    session: Session,
    tenant: Tenant,
    conv: Conversation,
    kind: str,
    params: dict[str, Any],
    risk: str,
    reason: str,
) -> ActionProposal:
    p = ActionProposal(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        kind=kind,
        params=params,
        risk=risk,
        reason=reason,
        state="proposed",
    )
    session.add(p)
    session.flush()
    return p


def _apply_extract(conv: Conversation, calls: list[ToolCall]) -> None:
    """extract_fields is safe to apply immediately: it only records what the customer said."""
    merged = dict(conv.extracted)
    for c in calls:
        if c.name == "extract_fields":
            fields = c.input.get("fields") or {}
            merged.update({str(k): str(v) for k, v in fields.items()})
    conv.extracted = merged


def _emergency_hit(pack: PackSpec, text: str) -> bool:
    low = text.lower()
    return any(k in low for k in pack.emergency_keywords)


def run_turn(
    session: Session, tenant: Tenant, pack: PackSpec, llm: LLMClient, conversation_id: uuid.UUID
) -> TurnResult:
    settings = get_settings()
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise LookupError(f"conversation {conversation_id} not found")
    if conv.status == "waiting_human":
        return TurnResult(conv.id, None, skipped_reason="waiting_human")
    if conv.status == "closed":
        return TurnResult(conv.id, None, skipped_reason="closed")
    contact = session.get(Contact, conv.contact_id)
    if contact is None or contact.consent.get("status") == "opted_out":
        return TurnResult(conv.id, None, skipped_reason="opted_out")

    history = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(settings.context_max_messages)
        )
    )[::-1]
    last_inbound = next((m for m in reversed(history) if m.direction == "inbound"), None)
    first_worker_reply = not any(
        m.direction == "outbound" and m.author == "worker" for m in history
    )

    proposal_ids: list[uuid.UUID] = []
    emergency = bool(last_inbound and _emergency_hit(pack, last_inbound.body))

    if emergency:
        # Keyword pre-check: no model in the loop for the dangerous branch.
        reply_text = pack.emergency_reply
        p = _store_proposal(
            session,
            tenant,
            conv,
            "escalate_emergency",
            {"summary": last_inbound.body[:500] if last_inbound else ""},
            "low",
            "emergency keyword",
        )
        proposal_ids.append(p.id)
        _audit(
            session, tenant.id, "turn.emergency_precheck", conversation_id=conv.id, proposal_id=p.id
        )
    else:
        system_volatile = tenant_facts(tenant)
        if conv.summary:
            system_volatile += f"\n\nSummary of the conversation so far:\n{conv.summary}"
        if first_worker_reply:
            system_volatile += f"\n\nThis is your first reply. Open with: {pack.intake_opening}"
        result = llm.complete(
            task="worker_turn",
            system_stable=pack.system_prompt,
            system_volatile=system_volatile,
            messages=build_messages(history),
            tools=pack.tools,
            max_tokens=1024,
        )
        _record_usage(session, tenant, conv.id, "worker_turn", result)
        reply_text = result.text or "Thanks, one moment while I check that with the team."
        _apply_extract(conv, result.tool_calls)
        for call in result.tool_calls:
            if call.name == "extract_fields":
                continue
            p = _store_proposal(
                session, tenant, conv, call.name, call.input, "low", "model proposal"
            )
            proposal_ids.append(p.id)
            if call.name == "hand_to_human":
                conv.status = "waiting_human"
        if (
            BOOKING_CLAIMS.search(reply_text)
            and not {c.name for c in result.tool_calls} & CLAIM_TOOLS
        ):
            p = _store_proposal(
                session,
                tenant,
                conv,
                "verify_claim",
                {"text": reply_text},
                "medium",
                "reply claims a booking without a proposal",
            )
            p.state = "awaiting"
            proposal_ids.append(p.id)
            _audit(
                session, tenant.id, "turn.verify_claim", conversation_id=conv.id, proposal_id=p.id
            )

    if first_worker_reply:
        disclosure = (
            str(tenant.settings.get("disclosure_text", ""))
            .format(business_name=tenant.name)
            .strip()
        )
        if disclosure:
            reply_text = f"{disclosure}\n\n{reply_text}"

    out = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="outbound",
        channel=conv.channel,
        author="worker",
        body=reply_text,
    )
    session.add(out)
    session.flush()
    send_message(session, tenant, out.id)
    conv.updated_at = datetime.now(UTC)
    if conv.status == "open":
        conv.status = "waiting_customer"

    total = len(history) + 1
    if total and total % settings.summary_every_messages == 0 and not emergency:
        summary = llm.complete(
            task="summarise",
            system_stable=SUMMARISE_PROMPT,
            system_volatile="",
            messages=build_messages(history + [out]),
            max_tokens=400,
        )
        _record_usage(session, tenant, conv.id, "summarise", summary)
        conv.summary = summary.text
    _audit(
        session,
        tenant.id,
        "turn.completed",
        conversation_id=conv.id,
        message_id=out.id,
        proposals=len(proposal_ids),
    )
    return TurnResult(conv.id, out.id, proposal_ids, emergency=emergency)
