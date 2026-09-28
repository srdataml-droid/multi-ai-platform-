"""One worker turn: rows in, one LLM call, rows out, the gate in between.

Context is built from the database every time, never from prior model output
alone, so a turn is reproducible from rows. The model gets the pack's stable
system prompt (cached), the tenant's facts, a stored summary if there is one, and
the last N messages as plain alternating turns.

Everything the model wants becomes a proposal, including the reply itself. The
gate assigns risk; `auto_approved` proposals execute now, `awaiting` ones notify
staff, `rejected` ones add a "a person will follow up" line to the reply. The
reply is executed last so it can carry that line.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.alerts import needs_a_person
from novaxis_core.approval_model import record_prediction
from novaxis_core.executors import execute
from novaxis_core.gate import Decision, GateContext, decide
from novaxis_core.intake import out_of_area, prompt_block
from novaxis_core.intake import status as intake_status
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
from novaxis_core.notify import enqueue_staff_notification
from novaxis_core.packspec import PackSpec
from novaxis_core.scheduling import appointments_block
from novaxis_core.sensitive import decrypt_fields
from novaxis_core.settings import get_settings
from novaxis_core.workflows import schedule_idle_steps

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
FALLBACK_REPLY = "Thanks, one moment while I check that with the team."


@dataclass
class TurnResult:
    conversation_id: uuid.UUID
    reply_message_id: uuid.UUID | None
    proposal_ids: list[uuid.UUID] = field(default_factory=list)
    decisions: dict[str, str] = field(default_factory=dict)
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


def disclosure_for(tenant: Tenant) -> str:
    """The AI disclosure opening a customer's first reply (and a phone call's greeting)."""
    # replace, not format: an owner's own braces in the text must not break every reply.
    disclosure = (
        str(tenant.settings.get("disclosure_text", ""))
        .replace("{business_name}", tenant.name)
        .strip()
    )
    privacy = str(tenant.settings.get("privacy_url") or "").strip()
    if privacy:
        disclosure = f"{disclosure} How we use your details: {privacy}".strip()
    return disclosure


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


def record_usage(
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


def ground_params(session: Session, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Replace facts the model asserts with facts the database holds, before the gate sees
    them. The gate is a pure function and cannot look anything up (ADR 0007), so a model's
    word must never decide a risk the rows can settle."""
    if kind == "confirm_appointment":
        from novaxis_core.models import Appointment

        try:
            appt = session.get(Appointment, uuid.UUID(str(params.get("appointment_id", ""))))
        except ValueError:
            appt = None
        if appt is not None:
            return {**params, "service_code": appt.service_code}
        return {**params, "service_code": ""}  # unknown appointment: no auto-confirm
    return params


def propose(
    session: Session,
    tenant: Tenant,
    conv: Conversation,
    kind: str,
    params: dict[str, Any],
    ctx: GateContext,
    origin: str,
) -> tuple[ActionProposal, Decision]:
    """Store one proposal with the gate's decision and act on it."""
    params = ground_params(session, kind, params)
    d = decide(kind, params, ctx)
    p = ActionProposal(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        kind=kind,
        params=params,
        risk=d.risk,
        reason=f"{origin}: {d.reason}",
        state=d.state,
    )
    session.add(p)
    session.flush()
    if d.state == "auto_approved":
        execute(session, tenant, p)
    elif d.state == "awaiting":
        record_prediction(session, tenant, p)
        enqueue_staff_notification(session, tenant, p.id)
    else:
        _audit(
            session, tenant.id, "proposal.rejected", proposal_id=p.id, kind=kind, reason=d.reason
        )
    return p, d


def _emergency_hit(pack: PackSpec, text: str) -> bool:
    low = text.lower()
    if any(k in low for k in pack.emergency_keywords):
        return True
    return bool(pack.emergency_check and pack.emergency_check(text))


def _service_code(pack: PackSpec, extracted: dict[str, Any]) -> str:
    ai = pack.after_intake
    if ai.service_code_from:
        value = str(extracted.get(ai.service_code_from, "")).strip().lower()
        for k, v in ai.service_code_map.items():
            if k.lower() == value:
                return v
    return ai.default_service_code


def _has_proposal(session: Session, conv: Conversation, kind: str) -> bool:
    return (
        session.scalar(
            select(ActionProposal.id).where(
                ActionProposal.conversation_id == conv.id,
                ActionProposal.kind == kind,
                ActionProposal.state.notin_(["rejected", "failed"]),
            )
        )
        is not None
    )


def run_turn(
    session: Session,
    tenant: Tenant,
    pack: PackSpec,
    llm: LLMClient,
    conversation_id: uuid.UUID,
    blocked_reason: str | None = None,
) -> TurnResult:
    """One worker turn. `blocked_reason` (a spent trial, see billing.py) stops the model and
    hands the conversation to a person; the emergency pre-check still runs, because it needs
    no model and a customer reporting a gas leak must never get silence."""
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
    ctx = GateContext(
        tenant_settings=tenant.settings,
        contact_consent=contact.consent,
        latest_inbound_text=last_inbound.body if last_inbound else "",
        conversation_channel=conv.channel,
        pack_rule=pack.rule,
    )
    result_ids: list[uuid.UUID] = []
    decisions: dict[str, str] = {}
    emergency = bool(last_inbound and _emergency_hit(pack, last_inbound.body))
    tool_calls: list[ToolCall] = []

    if blocked_reason and not emergency:
        conv.status = "waiting_human"
        needs_a_person(session, tenant.id, conv.id)
        _audit(
            session,
            tenant.id,
            "billing.worker_blocked",
            conversation_id=conv.id,
            reason=blocked_reason,
        )
        return TurnResult(conv.id, None, skipped_reason=blocked_reason)

    if tenant.settings.get("assistant") == "external" and not emergency:
        # The business's own agent answers through the agent API (agent.py). Only the
        # emergency pre-check above stays here: it needs no model, and it must never
        # depend on someone else's agent being up.
        from novaxis_core.agent_webhooks import enqueue

        enqueue(
            session,
            tenant.id,
            "message.received",
            {"conversation_id": str(conv.id), "channel": conv.channel},
            hand_over_if_undelivered=conv.id,
        )
        return TurnResult(conv.id, None, skipped_reason="external_agent")

    if emergency:
        # Keyword pre-check: no model in the loop for the dangerous branch.
        reply_text = pack.emergency_reply
        p, d = propose(
            session,
            tenant,
            conv,
            "escalate_emergency",
            {"summary": last_inbound.body[:500] if last_inbound else ""},
            ctx,
            "emergency keyword",
        )
        result_ids.append(p.id)
        decisions["escalate_emergency"] = d.state
        # Tell the customer someone was alerted only if an alert actually went out.
        alerted = p.state == "executed"
        reply_text = (
            f"{reply_text} {pack.emergency_alerted if alerted else pack.emergency_not_alerted}"
        ).strip()
        _audit(
            session,
            tenant.id,
            "turn.emergency_precheck",
            conversation_id=conv.id,
            proposal_id=p.id,
            alerted=alerted,
        )
    else:
        system_volatile = tenant_facts(tenant)
        if conv.summary:
            system_volatile += f"\n\nSummary of the conversation so far:\n{conv.summary}"
        if pack.intake:
            plain = decrypt_fields(conv.extracted, pack.sensitive_keys)
            system_volatile += "\n\n" + prompt_block(pack.intake, plain)
        appts = appointments_block(session, tenant, conv)
        if appts:
            system_volatile += "\n\n" + appts
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
        record_usage(session, tenant, conv.id, "worker_turn", result)
        reply_text = result.text or FALLBACK_REPLY
        tool_calls = result.tool_calls
        followup_needed = False
        for call in tool_calls:
            p, d = propose(session, tenant, conv, call.name, call.input, ctx, "model proposal")
            result_ids.append(p.id)
            decisions[call.name] = d.state
            if d.state == "rejected":
                followup_needed = True
        session.refresh(conv)
        plain = decrypt_fields(conv.extracted, pack.sensitive_keys)
        st = intake_status(pack.intake, plain) if pack.intake else None
        area_value = plain.get(pack.service_area_field) if pack.service_area_field else None
        if area_value and out_of_area(str(area_value), tenant.settings.get("service_area") or []):
            reply_text = pack.out_of_area_reply or reply_text
            if not _has_proposal(session, conv, "hand_to_human"):
                p, d = propose(
                    session,
                    tenant,
                    conv,
                    "hand_to_human",
                    {"reason": f"outside service area: {area_value}"},
                    ctx,
                    "service area",
                )
                result_ids.append(p.id)
                decisions["hand_to_human"] = d.state
        elif (
            st is not None
            and st.complete
            and pack.after_intake.action == "propose_appointment"
            and "propose_appointment" not in {c.name for c in tool_calls}
            and not _has_proposal(session, conv, "propose_appointment")
        ):
            # The model finished intake but did not propose; the engine does it for it.
            params = {
                "service_code": _service_code(pack, plain),
                "preferred_window": str(plain.get(pack.after_intake.window_from, "")),
                "notes": "proposed by intake engine",
            }
            p, d = propose(
                session, tenant, conv, "propose_appointment", params, ctx, "intake complete"
            )
            result_ids.append(p.id)
            decisions["propose_appointment"] = d.state
            tool_calls = [*tool_calls, ToolCall("propose_appointment", params, "engine")]
        if BOOKING_CLAIMS.search(reply_text) and not {c.name for c in tool_calls} & CLAIM_TOOLS:
            p, d = propose(
                session,
                tenant,
                conv,
                "verify_claim",
                {"text": reply_text},
                ctx,
                "reply claims a booking without a proposal",
            )
            result_ids.append(p.id)
            decisions["verify_claim"] = d.state
            _audit(
                session, tenant.id, "turn.verify_claim", conversation_id=conv.id, proposal_id=p.id
            )
        if followup_needed and pack.high_risk_followup not in reply_text:
            reply_text = f"{reply_text}\n\n{pack.high_risk_followup}"

    if first_worker_reply:
        disclosure = disclosure_for(tenant)
        if disclosure:
            reply_text = f"{disclosure}\n\n{reply_text}"

    # The reply is an action too. It goes through the gate like everything else, so an
    # opted-out contact or a safeguarding hit stops it here rather than in a special case.
    reply_p, reply_d = propose(session, tenant, conv, "reply", {"text": reply_text}, ctx, "reply")
    result_ids.append(reply_p.id)
    decisions["reply"] = reply_d.state
    reply_message_id: uuid.UUID | None = None
    if reply_p.state == "executed":
        reply_message_id = uuid.UUID(str(reply_p.result.get("message_id")))
    elif reply_d.state == "rejected":
        # The model's words were refused. Say something fixed and safe, then hand over.
        conv.status = "waiting_human"
        needs_a_person(session, tenant.id, conv.id)
        notice_p, notice_d = propose(
            session,
            tenant,
            conv,
            "handoff_notice",
            {"text": pack.handoff_notice},
            ctx,
            f"reply refused: {reply_d.reason}",
        )
        result_ids.append(notice_p.id)
        decisions["handoff_notice"] = notice_d.state
        if notice_p.state == "executed":
            reply_message_id = uuid.UUID(str(notice_p.result.get("message_id")))
        _audit(
            session, tenant.id, "turn.reply_refused", conversation_id=conv.id, reason=reply_d.reason
        )

    conv.updated_at = datetime.now(UTC)
    if conv.status == "open":
        conv.status = "waiting_customer"
    if reply_message_id and conv.status == "waiting_customer" and pack.workflows:
        schedule_idle_steps(session, tenant, pack, conv)

    total = len(history) + 1
    if reply_message_id and total % settings.summary_every_messages == 0 and not emergency:
        out = session.get(Message, reply_message_id)
        summary = llm.complete(
            task="summarise",
            system_stable=SUMMARISE_PROMPT,
            system_volatile="",
            messages=build_messages(history + ([out] if out else [])),
            max_tokens=400,
        )
        record_usage(session, tenant, conv.id, "summarise", summary)
        conv.summary = summary.text
    _audit(
        session,
        tenant.id,
        "turn.completed",
        conversation_id=conv.id,
        message_id=reply_message_id,
        proposals=len(result_ids),
    )
    return TurnResult(conv.id, reply_message_id, result_ids, decisions, emergency=emergency)
