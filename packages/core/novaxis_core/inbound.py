"""From a normalised inbound message to rows: contact, conversation, message, job.

Order matters and is fixed:
1. Idempotency: same provider_ref for this tenant and channel -> return what exists.
2. Opt-out: STOP and friends flip consent, send the confirmation, create no job.
3. Contact: match on phone (exact), email (lowercased) or visitor id. Never on name.
4. Conversation: the open one for this contact and channel, else a new one.
5. Message row, then a `worker_turn` job, then audit.

Everything runs inside the caller's tenant session, so RLS applies throughout.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.channels import NormalisedInbound, get_adapter
from novaxis_core.media import attach_media
from novaxis_core.models import (
    Appointment,
    AuditLog,
    Contact,
    Conversation,
    Job,
    Message,
    Tenant,
)

# Opt-out keywords are an SMS convention; they mean something only where we push messages.
# Web chat pushes nothing, so a visitor typing "stop" is simply talking. On SMS, "cancel"
# from someone with an upcoming appointment is about the appointment, not the subscription.
OPT_OUT_WORDS = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout"})
OPT_OUT_BY_CHANNEL: dict[str, frozenset[str]] = {
    "twilio_sms": OPT_OUT_WORDS,
    "email": frozenset({"stop", "unsubscribe"}),
    "whatsapp": frozenset({"stop", "unsubscribe"}),
}
OPT_IN_WORDS = frozenset({"start", "unstop", "yes", "subscribe"})
# Reminders say "Reply C to confirm". Recorded on the appointment; no model turn needed.
CONFIRM_WORDS = frozenset({"c", "confirm", "confirmed"})
OPT_OUT_CONFIRMATION = (
    "You have been unsubscribed and will receive no further messages from us. "
    "Reply START to opt back in."
)
OPT_IN_CONFIRMATION = "You are opted back in. How can we help?"


@dataclass(frozen=True)
class IngestResult:
    contact_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    job_id: uuid.UUID | None
    duplicate: bool = False
    opted_out: bool = False


def _keyword(body: str) -> str:
    return body.strip().lower().rstrip(".!")


def _has_upcoming_appointment(session: Session, contact: Contact) -> bool:
    return (
        session.scalar(
            select(Appointment.id)
            .where(
                Appointment.contact_id == contact.id,
                Appointment.status.in_(["held", "confirmed"]),
                Appointment.ends_at > datetime.now(UTC),
            )
            .limit(1)
        )
        is not None
    )


def is_opt_out(session: Session, contact: Contact, channel: str, word: str) -> bool:
    if word not in OPT_OUT_BY_CHANNEL.get(channel, frozenset()):
        return False
    if word == "cancel" and _has_upcoming_appointment(session, contact):
        return False  # the worker proposes cancel_appointment; staff approve it
    return True


def _audit(session: Session, tenant_id: uuid.UUID, event: str, **diff: object) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor="system:inbound",
            event=event,
            diff={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in diff.items()},
        )
    )


def find_or_create_contact(session: Session, tenant: Tenant, inbound: NormalisedInbound) -> Contact:
    stmt = select(Contact).where(Contact.merged_into.is_(None))
    if inbound.sender_phone:
        found = session.scalar(stmt.where(Contact.phones.contains([inbound.sender_phone])))
    elif inbound.sender_email:
        found = session.scalar(stmt.where(Contact.emails.contains([inbound.sender_email.lower()])))
    elif inbound.sender_visitor_id:
        found = session.scalar(
            stmt.where(Contact.visitor_ids.contains([inbound.sender_visitor_id]))
        )
    else:
        found = None
    if found is not None:
        if inbound.sender_name and not found.display_name:
            found.display_name = inbound.sender_name
        return found
    contact = Contact(
        tenant_id=tenant.id,
        display_name=inbound.sender_name,
        phones=[inbound.sender_phone] if inbound.sender_phone else [],
        emails=[inbound.sender_email.lower()] if inbound.sender_email else [],
        visitor_ids=[inbound.sender_visitor_id] if inbound.sender_visitor_id else [],
        consent={
            "status": "implied",
            "source": f"inbound_{inbound.channel}",
            "at": inbound.received_at.isoformat(),
        },
    )
    session.add(contact)
    session.flush()
    _audit(session, tenant.id, "contact.created", contact_id=contact.id, channel=inbound.channel)
    return contact


def _open_conversation(
    session: Session, tenant: Tenant, contact: Contact, channel: str
) -> Conversation:
    conv = session.scalar(
        select(Conversation)
        .where(
            Conversation.contact_id == contact.id,
            Conversation.channel == channel,
            Conversation.status != "closed",
        )
        .order_by(Conversation.created_at.desc())
    )
    if conv is None:
        conv = Conversation(tenant_id=tenant.id, contact_id=contact.id, channel=channel)
        session.add(conv)
        session.flush()
        _audit(session, tenant.id, "conversation.opened", conversation_id=conv.id, channel=channel)
    return conv


def _store_inbound(
    session: Session, tenant: Tenant, conv: Conversation, inbound: NormalisedInbound
) -> Message:
    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="inbound",
        channel=inbound.channel,
        author="customer",
        body=inbound.body,
        provider_ref=inbound.provider_ref,
        delivered_at=inbound.received_at,
    )
    session.add(msg)
    session.flush()
    if inbound.media:
        attach_media(session, tenant, msg, inbound.media)
    return msg


def _send_now(
    session: Session, tenant: Tenant, contact: Contact, conv: Conversation, channel: str, text: str
) -> Message:
    """Synchronous send for opt-out confirmations only. Everything else is a job."""
    adapter = get_adapter(channel)
    to = contact.phones[0] if contact.phones else (contact.emails[0] if contact.emails else "")
    cfg = tenant.settings.get("channels", {}).get(channel, {}).get("config", {})
    ref = adapter.send(to=to, body=text, tenant_channel_config=cfg) if to else None
    out = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="outbound",
        channel=channel,
        author="system",
        body=text,
        provider_ref=ref.provider_ref if ref else None,
        delivered_at=datetime.now(UTC) if ref else None,
    )
    session.add(out)
    session.flush()
    return out


def _record_attendance(
    session: Session, tenant: Tenant, contact: Contact, conv: Conversation
) -> uuid.UUID | None:
    """ "C" to a reminder: mark the next confirmed appointment and say thanks. Returns the
    send job, or None if there is nothing to confirm (then it is an ordinary message)."""
    appt = session.scalar(
        select(Appointment)
        .where(
            Appointment.contact_id == contact.id,
            Appointment.status == "confirmed",
            Appointment.starts_at > datetime.now(UTC),
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    )
    if appt is None:
        return None
    from novaxis_core.scheduling import _enqueue_send, fmt, location_for, tz_for

    appt.customer_confirmed_at = datetime.now(UTC)
    when = fmt(appt.starts_at, tz_for(tenant, location_for(session, tenant)))
    job = _enqueue_send(
        session, tenant, conv, f"Thanks, that's confirmed for {when}. See you then."
    )
    _audit(session, tenant.id, "appointment.customer_confirmed", appointment_id=appt.id)
    return job.id


def ingest(session: Session, tenant: Tenant, inbound: NormalisedInbound) -> IngestResult:
    existing = session.scalar(
        select(Message).where(
            Message.direction == "inbound",
            Message.channel == inbound.channel,
            Message.provider_ref == inbound.provider_ref,
        )
    )
    if existing is not None:
        conv = session.get(Conversation, existing.conversation_id)
        assert conv is not None
        return IngestResult(conv.contact_id, conv.id, existing.id, None, duplicate=True)

    contact = find_or_create_contact(session, tenant, inbound)
    word = _keyword(inbound.body)

    if is_opt_out(session, contact, inbound.channel, word):
        contact.consent = {
            **contact.consent,
            "status": "opted_out",
            "at": inbound.received_at.isoformat(),
            "channel": inbound.channel,
        }
        conv = _open_conversation(session, tenant, contact, inbound.channel)
        msg = _store_inbound(session, tenant, conv, inbound)
        _send_now(session, tenant, contact, conv, inbound.channel, OPT_OUT_CONFIRMATION)
        conv.status = "closed"
        _audit(
            session, tenant.id, "contact.opted_out", contact_id=contact.id, channel=inbound.channel
        )
        return IngestResult(contact.id, conv.id, msg.id, None, opted_out=True)

    if contact.consent.get("status") == "opted_out":
        conv = _open_conversation(session, tenant, contact, inbound.channel)
        msg = _store_inbound(session, tenant, conv, inbound)
        if word in OPT_IN_WORDS and inbound.channel in OPT_OUT_BY_CHANNEL:
            contact.consent = {
                **contact.consent,
                "status": "implied",
                "at": inbound.received_at.isoformat(),
            }
            _audit(session, tenant.id, "contact.opted_in", contact_id=contact.id)
            _send_now(session, tenant, contact, conv, inbound.channel, OPT_IN_CONFIRMATION)
            return IngestResult(contact.id, conv.id, msg.id, None)
        # Opted out and not opting in: keep the record, never reply, never enqueue.
        conv.status = "closed"
        return IngestResult(contact.id, conv.id, msg.id, None, opted_out=True)

    conv = _open_conversation(session, tenant, contact, inbound.channel)
    msg = _store_inbound(session, tenant, conv, inbound)
    conv.updated_at = datetime.now(UTC)
    if word in CONFIRM_WORDS:
        confirmed = _record_attendance(session, tenant, contact, conv)
        if confirmed is not None:
            return IngestResult(contact.id, conv.id, msg.id, confirmed)
    if conv.status == "waiting_customer":
        conv.status = "open"
    job = Job(
        tenant_id=tenant.id,
        kind="worker_turn",
        payload={"conversation_id": str(conv.id), "message_id": str(msg.id)},
    )
    session.add(job)
    session.flush()
    _audit(session, tenant.id, "message.received", message_id=msg.id, job_id=job.id)
    return IngestResult(contact.id, conv.id, msg.id, job.id)
