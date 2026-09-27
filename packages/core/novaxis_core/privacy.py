"""A customer's data rights and the business's retention period.

- `export_contact`: everything we hold about one customer, for an access request.
- `erase_contact`: delete one customer and everything that names them (conversations,
  messages, photos, bookings, approvals, queued jobs, bridge hand-offs).
- `purge_expired`: erase every customer with no activity inside the business's
  `retention_days`. Runs daily per business.

Erasure runs as the service role with an explicit tenant filter on every statement, because
the app role cannot delete messages (the message log is append-only for everyone else).
The audit log keeps event names and ids, never message text; it is not erased. Whether that
meets each business's obligations is for its data-protection adviser [VERIFY].
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.orm import Session

from novaxis_core.models import (
    ActionProposal,
    Appointment,
    Approval,
    AuditLog,
    BridgeTicket,
    Contact,
    Conversation,
    Job,
    Message,
    Tenant,
)
from novaxis_core.sensitive import decrypt_fields
from novaxis_core.storage import get_store

PURGE_KIND = "retention_purge"


def _deleted(session: Session, stmt: Any) -> int:
    return int(getattr(session.execute(stmt), "rowcount", 0) or 0)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def export_contact(
    session: Session, contact: Contact, sensitive_keys: frozenset[str]
) -> dict[str, Any]:
    """One customer's data as plain JSON. Sensitive intake answers are decrypted: the person
    asking is the person they are about."""
    people = [
        contact.id,
        *session.scalars(select(Contact.id).where(Contact.merged_into == contact.id)),
    ]
    convs = list(
        session.scalars(
            select(Conversation)
            .where(Conversation.contact_id.in_(people))
            .order_by(Conversation.created_at)
        )
    )
    out_convs = []
    for c in convs:
        msgs = session.scalars(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)
        )
        out_convs.append(
            {
                "id": str(c.id),
                "channel": c.channel,
                "status": c.status,
                "started_at": _iso(c.created_at),
                "details_given": decrypt_fields(dict(c.extracted or {}), sensitive_keys),
                "summary": c.summary,
                "messages": [
                    {
                        "at": _iso(m.created_at),
                        "from": "customer" if m.direction == "inbound" else m.author,
                        "text": m.body,
                        "files": [str(x.get("key", "")) for x in (m.media or [])],
                    }
                    for m in msgs
                ],
            }
        )
    appts = session.scalars(
        select(Appointment)
        .where(Appointment.contact_id.in_(people))
        .order_by(Appointment.starts_at)
    )
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "contact": {
            "id": str(contact.id),
            "name": contact.display_name,
            "phones": contact.phones,
            "emails": contact.emails,
            "consent": contact.consent,
            "first_seen": _iso(contact.created_at),
        },
        "conversations": out_convs,
        "appointments": [
            {
                "service": a.service_code,
                "starts_at": _iso(a.starts_at),
                "ends_at": _iso(a.ends_at),
                "status": a.status,
                "notes": a.notes,
            }
            for a in appts
        ],
    }


def erase_contact(
    session: Session, tenant_id: uuid.UUID, contact_id: uuid.UUID, actor: str, reason: str
) -> dict[str, int]:
    """Delete one customer and everything that names them. `session` must be a service
    session; every statement is filtered by `tenant_id`. Files are deleted first, so a
    storage failure aborts before any row is removed."""
    people = list(
        session.scalars(
            select(Contact.id).where(
                Contact.tenant_id == tenant_id,
                or_(Contact.id == contact_id, Contact.merged_into == contact_id),
            )
        )
    )
    if contact_id not in people:
        raise LookupError("contact not found")
    conv_ids = list(
        session.scalars(
            select(Conversation.id).where(
                Conversation.tenant_id == tenant_id, Conversation.contact_id.in_(people)
            )
        )
    )
    msgs = list(
        session.execute(
            select(Message.id, Message.media).where(
                Message.tenant_id == tenant_id, Message.conversation_id.in_(conv_ids)
            )
        )
    )
    appt_ids = list(
        session.scalars(
            select(Appointment.id).where(
                Appointment.tenant_id == tenant_id,
                or_(
                    Appointment.contact_id.in_(people),
                    Appointment.conversation_id.in_(conv_ids),
                ),
            )
        )
    )
    prop_ids = list(
        session.scalars(
            select(ActionProposal.id).where(
                ActionProposal.tenant_id == tenant_id,
                ActionProposal.conversation_id.in_(conv_ids),
            )
        )
    )

    files = [str(f["key"]) for _, media in msgs for f in (media or []) if f.get("key")]
    if files:
        store = get_store()
        for key in files:
            if not key.startswith(f"{tenant_id}/"):
                raise ValueError("a file outside this business's storage was referenced")
            store.delete(key)

    as_text = [str(x) for x in (*conv_ids, *appt_ids, *(m for m, _ in msgs))]
    counts = {"contacts": len(people), "conversations": len(conv_ids), "messages": len(msgs)}
    counts["files"] = len(files)
    counts["jobs"] = _deleted(
        session,
        delete(Job).where(
            Job.tenant_id == tenant_id,
            or_(
                Job.payload["conversation_id"].astext.in_(as_text),
                Job.payload["appointment_id"].astext.in_(as_text),
                Job.payload["message_id"].astext.in_(as_text),
            ),
        ),
    )
    counts["bridge_tickets"] = _deleted(
        session,
        delete(BridgeTicket).where(
            BridgeTicket.tenant_id == tenant_id,
            BridgeTicket.details["appointment_id"].astext.in_([str(a) for a in appt_ids]),
        ),
    )
    session.execute(
        delete(Approval).where(Approval.tenant_id == tenant_id, Approval.proposal_id.in_(prop_ids))
    )
    counts["appointments"] = _deleted(
        session,
        delete(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.id.in_(appt_ids)),
    )
    session.execute(
        delete(ActionProposal).where(
            ActionProposal.tenant_id == tenant_id, ActionProposal.id.in_(prop_ids)
        )
    )
    session.execute(
        delete(Message).where(Message.tenant_id == tenant_id, Message.conversation_id.in_(conv_ids))
    )
    session.execute(
        delete(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.id.in_(conv_ids)
        )
    )
    session.execute(
        delete(Contact).where(
            Contact.tenant_id == tenant_id, Contact.id.in_(people), Contact.id != contact_id
        )
    )
    session.execute(delete(Contact).where(Contact.tenant_id == tenant_id, Contact.id == contact_id))
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            event="contact.erased",
            subject_table="contacts",
            subject_id=contact_id,
            diff={"reason": reason, **counts},
        )
    )
    session.flush()
    return counts


def expired_contacts(
    session: Session, tenant: Tenant, now: datetime | None = None, limit: int = 200
) -> list[uuid.UUID]:
    """Customers of this business with nothing (message, conversation, booking) inside the
    retention period. Merged pointers go with the contact they point to."""
    days = int(tenant.settings.get("retention_days") or 730)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    recent_msg = (
        select(Message.id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.contact_id == Contact.id, Message.created_at >= cutoff)
    )
    recent_conv = select(Conversation.id).where(
        Conversation.contact_id == Contact.id, Conversation.created_at >= cutoff
    )
    recent_appt = select(Appointment.id).where(
        Appointment.contact_id == Contact.id,
        or_(Appointment.ends_at >= cutoff, Appointment.created_at >= cutoff),
    )
    return list(
        session.scalars(
            select(Contact.id)
            .where(
                Contact.tenant_id == tenant.id,
                Contact.merged_into.is_(None),
                Contact.created_at < cutoff,
                ~exists(recent_msg),
                ~exists(recent_conv),
                ~exists(recent_appt),
            )
            .limit(limit)
        )
    )


def purge_expired(session: Session, tenant: Tenant, now: datetime | None = None) -> int:
    """Erase every expired customer of one business. `session` must be a service session."""
    ids = expired_contacts(session, tenant, now)
    for cid in ids:
        erase_contact(session, tenant.id, cid, "system:retention", "retention period ended")
    return len(ids)


def enqueue_purges(
    session: Session, tenant_ids: list[uuid.UUID], min_interval: timedelta = timedelta(days=1)
) -> int:
    """Called on the worker's timer with a service session: one purge per business per day."""
    since = datetime.now(UTC) - min_interval
    n = 0
    for tid in tenant_ids:
        recent = session.scalar(
            select(Job.id)
            .where(Job.kind == PURGE_KIND, Job.tenant_id == tid, Job.created_at >= since)
            .limit(1)
        )
        if recent is None:
            session.add(Job(tenant_id=tid, kind=PURGE_KIND, payload={}))
            n += 1
    session.flush()
    return n
