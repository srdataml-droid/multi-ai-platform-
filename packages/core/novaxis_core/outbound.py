"""Send one stored outbound message through its channel. Used by the
`send_message` job kind (Chunk 3 wires the job runner)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_core.channels import get_adapter
from novaxis_core.models import Contact, Conversation, Message, Tenant

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
    if msg.channel == "whatsapp":
        last = session.scalar(
            select(func.max(Message.created_at)).where(
                Message.conversation_id == conv.id, Message.direction == "inbound"
            )
        )
        if last is None or datetime.now(UTC) - last > WHATSAPP_WINDOW:
            raise ReplyWindowClosedError(
                "outside WhatsApp's 24-hour reply window: an approved template is needed"
            )
    cfg = tenant.settings.get("channels", {}).get(msg.channel, {}).get("config", {})
    ref = get_adapter(msg.channel).send(
        to=destination_for(contact, msg.channel), body=msg.body, tenant_channel_config=cfg
    )
    # provider_ref and delivered_at are the only columns the app may set after insert,
    # via a dedicated grant (migration 0002), because messages are otherwise append-only.
    msg.provider_ref = ref.provider_ref
    msg.delivered_at = datetime.now(UTC)
    session.flush()
    return msg
