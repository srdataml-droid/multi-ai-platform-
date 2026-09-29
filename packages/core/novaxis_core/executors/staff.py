"""Executors that change conversation state or reach staff: extract, hand off, escalate, verify."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.alerts import alert_staff, needs_a_person
from novaxis_core.booking_types import intake_for, sensitive_keys_for
from novaxis_core.channels import get_adapter
from novaxis_core.executors import ExecResult, conversation_id_of, executor
from novaxis_core.intake import valid_answer
from novaxis_core.models import ActionProposal, Conversation, Tenant
from novaxis_core.pack_registry import resolve_pack
from novaxis_core.sensitive import decrypt_fields, encrypt_fields


@executor("extract_fields")
def extract_fields(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    pack = resolve_pack(tenant.pack_id)
    private = sensitive_keys_for(tenant, pack)
    current = decrypt_fields(conv.extracted, private)
    questions = {q.key: q for q in intake_for(session, tenant, pack, conv, current).questions}
    fields: dict[str, str] = {}
    kept: list[str] = []
    for k, v in params.fields.items():
        key, value = str(k), str(v)
        q = questions.get(key)
        # A good answer is never replaced by one the intake engine rejects: live, the
        # model rewrote a recorded "yes" as "high", intake fell back to incomplete and
        # the booking was never proposed.
        if q and key in current and valid_answer(q, str(current[key])):
            if not valid_answer(q, value):
                kept.append(key)
                continue
        fields[key] = value
    merged = dict(conv.extracted)
    merged.update(encrypt_fields(fields, private))
    conv.extracted = merged
    # Keys only: values may be sensitive and this result is audited.
    result = {"keys": ",".join(sorted(fields))}
    if kept:
        result["kept"] = ",".join(sorted(kept))
    return ExecResult(True, result)


@executor("hand_to_human")
def hand_to_human(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    if conv.status not in ("closed", "waiting_human"):
        conv.status = "waiting_human"
        needs_a_person(session, tenant.id, conv.id)
    return ExecResult(True, {"reason": params.reason[:200]})


@executor("escalate_emergency")
def escalate_emergency(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    """Alert every escalation contact on every channel they have. Partial failure is
    still success if at least one alert went out; total failure is recorded, not raised."""
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is not None and conv.status != "closed":
        conv.status = "waiting_human"
    contacts = tenant.settings.get("escalation_contacts") or []
    channels = tenant.settings.get("channels") or {}
    text = f"EMERGENCY from a customer of {tenant.name}: {params.summary[:400]}"
    if conv is not None:
        text += f"\nConversation: {conv.id}"
    sent: list[str] = []
    failed: list[str] = []
    for c in contacts:
        for channel, to in (("twilio_sms", c.get("phone")), ("email", c.get("email"))):
            if not to:
                continue
            cfg = (channels.get(channel) or {}).get("config") or {}
            try:
                get_adapter(channel).send(to=to, body=text, tenant_channel_config=cfg)
                sent.append(f"{channel}:{to}")
            except Exception as exc:  # noqa: BLE001 - keep trying the other contacts
                failed.append(f"{channel}:{to}:{type(exc).__name__}")
    pushed = alert_staff(
        session,
        tenant,
        "EMERGENCY: a customer needs you now",
        "A customer reported an emergency. Open the conversation straight away.",
        f"/conversations/{conv.id}" if conv is not None else "/inbox",
        urgent=True,
    )
    if pushed:
        sent.append(f"push:{pushed}")
    if not contacts and not pushed:
        return ExecResult(False, {"sent": "", "failed": ""}, "tenant has no escalation contacts")
    ok = bool(sent)
    return ExecResult(
        ok,
        {"sent": ",".join(sent), "failed": ",".join(failed)},
        None if ok else "no alert delivered",
    )


@executor("verify_claim")
def verify_claim(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    """Approval of a claim check means a person looked. Nothing else to do."""
    return ExecResult(True, {"verified": True})
