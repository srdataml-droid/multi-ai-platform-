"""Send one stored outbound message through its channel. Used by the
`send_message` job kind (Chunk 3 wires the job runner)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_core.channels import get_adapter
from novaxis_core.channels.base import ProviderRef
from novaxis_core.channels.whatsapp import (
    MAX_TEMPLATE_TEXT,
    WhatsAppAdapter,
    template_param,
    update_template,
)
from novaxis_core.models import AuditLog, Contact, Conversation, Message, Tenant

WHATSAPP_WINDOW = timedelta(hours=24)


class ReplyWindowClosedError(PermissionError):
    """WhatsApp allows free-form messages only within 24 hours of the customer's last one."""


def destination_for(contact: Contact, channel: str) -> str:
    if channel in ("twilio_sms", "whatsapp"):
        return contact.phones[0] if contact.phones else ""
    if channel == "email":
        return contact.emails[0] if contact.emails else ""
    if channel == "webchat":
        return contact.visitor_ids[0] if contact.visitor_ids else ""
    return ""


def send_message(session: Session, tenant: Tenant, message_id: uuid.UUID) -> Message:
    """Idempotent: a message with a provider_ref has already been sent."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise LookupError(f"message {message_id} not found")
    if msg.direction != "outbound":
        raise ValueError("only outbound messages can be sent")
    if msg.provider_ref:
        return msg
    conv = session.get(Conversation, msg.conversation_id)
    if conv is None:
        raise LookupError("message has no conversation")
    contact = session.get(Contact, conv.contact_id)
    if contact is None:
        raise LookupError("conversation has no contact")
    if contact.consent.get("status") == "opted_out":
        raise PermissionError("contact has opted out")
    cfg = tenant.settings.get("channels", {}).get(msg.channel, {}).get("config", {})
    to = destination_for(contact, msg.channel)
    if msg.channel == "whatsapp" and not _window_open(session, conv):
        ref = _send_update_template(session, tenant, contact, msg, to, cfg)
    else:
        ref = get_adapter(msg.channel).send(to=to, body=msg.body, tenant_channel_config=cfg)
    # provider_ref and delivered_at are the only columns the app may set after insert,
    # via a dedicated grant (migration 0002), because messages are otherwise append-only.
    msg.provider_ref = ref.provider_ref
    msg.delivered_at = datetime.now(UTC)
    session.flush()
    return msg


def _window_open(session: Session, conv: Conversation) -> bool:
    last = session.scalar(
        select(func.max(Message.created_at)).where(
            Message.conversation_id == conv.id, Message.direction == "inbound"
        )
    )
    return last is not None and datetime.now(UTC) - last <= WHATSAPP_WINDOW


def _send_update_template(
    session: Session,
    tenant: Tenant,
    contact: Contact,
    msg: Message,
    to: str,
    cfg: dict[str, Any],
) -> ProviderRef:
    """Outside the 24 hours: the message goes out whole inside the business's approved
    update template. Never shortened: a message too long for it goes to a person."""
    template = update_template(cfg)
    if template is None:
        raise ReplyWindowClosedError(
            "outside WhatsApp's 24-hour reply window and the business has no approved "
            "update template"
        )
    text = template_param(msg.body)
    if len(text) > MAX_TEMPLATE_TEXT:
        raise ReplyWindowClosedError(
            "outside WhatsApp's 24-hour reply window and the message is too long for the "
            "update template"
        )
    # The name comes from the customer's own WhatsApp profile: keep it short.
    name = template_param(contact.display_name or "")[:60].strip() or "there"
    adapter = get_adapter("whatsapp")
    if not isinstance(adapter, WhatsAppAdapter):
        raise TypeError("the whatsapp channel has no template sending")
    ref = adapter.send_template(
        to=to,
        name=template["name"],
        language=template["language"],
        params=[name, tenant.name, text],
        tenant_channel_config=cfg,
    )
    # The transcript keeps the message as written; the audit log records that it went
    # inside the template (and so is charged by Meta as a template message).
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor="worker:whatsapp",
            event="whatsapp.template_sent",
            subject_table="messages",
            subject_id=msg.id,
            diff={"template": template["name"], "language": template["language"]},
        )
    )
    return ref
