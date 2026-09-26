"""Executors that change conversation state or reach staff: extract, hand off, escalate, verify."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.channels import get_adapter
from novaxis_core.executors import ExecResult, conversation_id_of, executor
from novaxis_core.models import ActionProposal, Conversation, Tenant
from novaxis_core.pack_registry import resolve_pack
from novaxis_core.sensitive import encrypt_fields


@executor("extract_fields")
def extract_fields(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    sensitive = resolve_pack(tenant.pack_id).sensitive_keys
    merged = dict(conv.extracted)
    merged.update(encrypt_fields({str(k): str(v) for k, v in params.fields.items()}, sensitive))
    conv.extracted = merged
    # Keys only: values may be sensitive and this result is audited.
    return ExecResult(True, {"keys": ",".join(sorted(params.fields))})


@executor("hand_to_human")
def hand_to_human(
    session: Session, tenant: Tenant, proposal: ActionProposal, params: Any
) -> ExecResult:
    conv = session.get(Conversation, conversation_id_of(proposal))
    if conv is None:
        return ExecResult(False, {}, "conversation not found")
    if conv.status != "closed":
        conv.status = "waiting_human"
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
    if not contacts:
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
