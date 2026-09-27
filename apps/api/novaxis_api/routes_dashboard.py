"""Read models for the dashboard: inbox, work queue, contacts, analytics, and the
conversation actions staff take (take over, hand back, send, suggest)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.billing import trial_block_reason
from novaxis_core.contacts import merge, possible_duplicates
from novaxis_core.llm import build_llm
from novaxis_core.models import (
    ActionProposal,
    Appointment,
    AuditLog,
    Contact,
    Conversation,
    Job,
    Message,
    MetricsDaily,
    Tenant,
)
from novaxis_core.privacy import erase_contact, export_contact
from novaxis_core.sensitive import reveal
from novaxis_core.turn import build_messages, record_usage, tenant_facts
from novaxis_db.session import service_session
from novaxis_packs import get_pack

router = APIRouter(tags=["dashboard"])
STAFF = {"owner", "staff", "operator"}


def _tenant(session: TenantDb) -> Tenant:
    t = session.scalar(select(Tenant))
    assert t is not None
    return t


def _bucket(conv: Conversation, awaiting: int, emergency: bool, has_worker_reply: bool) -> str:
    if emergency:
        return "emergencies"
    if conv.status == "waiting_human":
        return "human_review"
    if awaiting:
        return "awaiting_approval"
    if conv.status == "closed":
        return "done"
    if conv.status == "waiting_customer":
        return "waiting"
    return "new" if not has_worker_reply else "open"


def _conversation_rows(
    session: TenantDb, role: str, statuses: list[str] | None, limit: int
) -> list[dict[str, Any]]:
    tenant = _tenant(session)
    pack = get_pack(tenant.pack_id)
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    if statuses:
        stmt = stmt.where(Conversation.status.in_(statuses))
    convs = list(session.scalars(stmt))
    if not convs:
        return []
    ids = [c.id for c in convs]
    contacts = {
        c.id: c
        for c in session.scalars(
            select(Contact).where(Contact.id.in_([c.contact_id for c in convs]))
        )
    }
    awaiting = dict(
        session.execute(
            select(ActionProposal.conversation_id, func.count())
            .where(ActionProposal.conversation_id.in_(ids), ActionProposal.state == "awaiting")
            .group_by(ActionProposal.conversation_id)
        ).all()
    )
    emergencies = {
        r[0]
        for r in session.execute(
            select(ActionProposal.conversation_id).where(
                ActionProposal.conversation_id.in_(ids), ActionProposal.kind == "escalate_emergency"
            )
        )
    }
    last_msgs: dict[uuid.UUID, Message] = {}
    unread: dict[uuid.UUID, int] = {}
    worker_replied: set[uuid.UUID] = set()
    for m in session.scalars(
        select(Message).where(Message.conversation_id.in_(ids)).order_by(Message.created_at)
    ):
        last_msgs[m.conversation_id] = m
        if m.direction == "outbound":
            unread[m.conversation_id] = 0
            if m.author == "worker":
                worker_replied.add(m.conversation_id)
        else:
            unread[m.conversation_id] = unread.get(m.conversation_id, 0) + 1
    rows: list[dict[str, Any]] = []
    for c in convs:
        contact = contacts.get(c.contact_id)
        last = last_msgs.get(c.id)
        fields = reveal(c.extracted, pack.sensitive_keys, role)
        rows.append(
            {
                "id": str(c.id),
                "channel": c.channel,
                "status": c.status,
                "bucket": _bucket(
                    c, awaiting.get(c.id, 0), c.id in emergencies, c.id in worker_replied
                ),
                "contact": {
                    "id": str(c.contact_id),
                    "display_name": contact.display_name if contact else None,
                },
                "last_message": {
                    "body": last.body[:140],
                    "direction": last.direction,
                    "at": last.created_at.isoformat(),
                }
                if last
                else None,
                "unread": unread.get(c.id, 0),
                "awaiting": awaiting.get(c.id, 0),
                "columns": {col.key: fields.get(col.key) for col in pack.dashboard.inbox_columns},
                "updated_at": c.updated_at.isoformat(),
            }
        )
    return rows


@router.get("/inbox")
def inbox(
    principal: CurrentPrincipal,
    session: TenantDb,
    status_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    statuses = [s for s in (status_filter or "").split(",") if s] or None
    tenant = _tenant(session)
    pack = get_pack(tenant.pack_id)
    return {
        "columns": [c.model_dump() for c in pack.dashboard.inbox_columns],
        "labels": pack.dashboard.labels,
        "items": _conversation_rows(session, principal.role, statuses, limit),
    }


@router.get("/work-queue")
def work_queue(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    tenant = _tenant(session)
    pack = get_pack(tenant.pack_id)
    rows = _conversation_rows(
        session, principal.role, ["open", "waiting_human", "waiting_customer"], 200
    )
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r["bucket"], []).append(r)
    order = ["emergencies", "human_review", "awaiting_approval", "new", "open", "waiting", "done"]
    return {
        "buckets": [
            {
                "key": k,
                "label": pack.dashboard.labels.get(k, k.replace("_", " ")),
                "items": buckets.get(k, []),
            }
            for k in order
            if buckets.get(k)
        ],
        "pack_buckets": pack.dashboard.work_queue_buckets,
    }


@router.get("/contacts")
def contacts(
    principal: CurrentPrincipal, session: TenantDb, q: str | None = None, limit: int = 100
) -> dict[str, Any]:
    stmt = (
        select(Contact)
        .where(Contact.merged_into.is_(None))
        .order_by(Contact.created_at.desc())
        .limit(limit)
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Contact.display_name).like(like),
                func.array_to_string(Contact.phones, ",").like(like),
                func.array_to_string(Contact.emails, ",").like(like),
            )
        )
    rows = list(session.scalars(stmt))
    staff = principal.role in STAFF
    dupes = possible_duplicates(session, rows) if staff else {}
    return {
        "items": [
            {
                "id": str(c.id),
                "display_name": c.display_name,
                "phones": c.phones if staff else [p[:4] + "..." for p in c.phones],
                "emails": c.emails if staff else ["hidden"] * len(c.emails),
                "consent": c.consent.get("status"),
                "created_at": c.created_at.isoformat(),
                "possible_duplicates": [
                    {"id": str(d.id), "display_name": d.display_name or "Unknown"}
                    for d in dupes.get(c.id, [])
                ],
            }
            for c in rows
        ]
    }


class MergeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    into: uuid.UUID


@router.post("/contacts/{contact_id}/merge")
def merge_contact(
    contact_id: uuid.UUID, body: MergeBody, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Staff confirm that two contacts are the same person. The one merged into keeps its
    record; the other's conversations and bookings move to it."""
    if principal.role not in STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    drop = session.get(Contact, contact_id)
    keep = session.get(Contact, body.into)
    if drop is None or keep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    try:
        merge(session, principal.tenant_id, keep, drop, f"user:{principal.user_id}")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"id": str(keep.id)}


@router.get("/analytics")
def analytics(principal: CurrentPrincipal, session: TenantDb, days: int = 30) -> dict[str, Any]:
    since = (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)
    rows = list(
        session.scalars(
            select(MetricsDaily).where(MetricsDaily.day >= since).order_by(MetricsDaily.day)
        )
    )
    totals = {
        k: 0
        for k in (
            "inbound",
            "answered_under_10s",
            "intake_completed",
            "bookings_proposed",
            "bookings_approved",
            "escalations",
            "human_takeovers",
        )
    }
    for r in rows:
        for k in totals:
            totals[k] += int(getattr(r, k))
    return {
        "days": days,
        "totals": totals,
        "series": [
            {
                "day": r.day.date().isoformat(),
                "channel": r.channel,
                **{k: int(getattr(r, k)) for k in totals},
            }
            for r in rows
        ],
    }


class StaffMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


def _get_conv(session: TenantDb, conversation_id: uuid.UUID) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such conversation")
    return conv


def _require_staff(principal: CurrentPrincipal) -> None:
    if principal.role not in STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "viewers cannot act on conversations")


@router.post("/conversations/{conversation_id}/takeover")
def takeover(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    _require_staff(principal)
    conv = _get_conv(session, conversation_id)
    conv.status = "waiting_human"
    conv.owner_user_id = principal.user_id
    conv.takeover_at = datetime.now(UTC)
    session.add(
        AuditLog(
            tenant_id=conv.tenant_id,
            actor=f"user:{principal.user_id}",
            event="conversation.takeover",
            subject_table="conversations",
            subject_id=conv.id,
            diff={},
        )
    )
    return {"id": str(conv.id), "status": conv.status}


@router.post("/conversations/{conversation_id}/handback")
def handback(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    _require_staff(principal)
    conv = _get_conv(session, conversation_id)
    conv.status = "waiting_customer"
    conv.owner_user_id = None
    session.add(
        AuditLog(
            tenant_id=conv.tenant_id,
            actor=f"user:{principal.user_id}",
            event="conversation.handback",
            subject_table="conversations",
            subject_id=conv.id,
            diff={},
        )
    )
    return {"id": str(conv.id), "status": conv.status}


@router.post("/conversations/{conversation_id}/close")
def close(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    _require_staff(principal)
    conv = _get_conv(session, conversation_id)
    conv.status = "closed"
    session.add(
        AuditLog(
            tenant_id=conv.tenant_id,
            actor=f"user:{principal.user_id}",
            event="conversation.closed",
            subject_table="conversations",
            subject_id=conv.id,
            diff={},
        )
    )
    return {"id": str(conv.id), "status": conv.status}


@router.post("/conversations/{conversation_id}/messages")
def staff_send(
    conversation_id: uuid.UUID, body: StaffMessage, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """A person writes to the customer. Consent is still checked by the send job."""
    _require_staff(principal)
    conv = _get_conv(session, conversation_id)
    contact = session.get(Contact, conv.contact_id)
    if contact is not None and contact.consent.get("status") == "opted_out":
        raise HTTPException(status.HTTP_409_CONFLICT, "contact has opted out")
    msg = Message(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        direction="outbound",
        channel=conv.channel,
        author="human",
        body=body.body,
    )
    session.add(msg)
    session.flush()
    session.add(
        Job(tenant_id=conv.tenant_id, kind="send_message", payload={"message_id": str(msg.id)})
    )
    if conv.status != "waiting_human":
        conv.status = "waiting_human"
        conv.owner_user_id = principal.user_id
    conv.updated_at = datetime.now(UTC)
    return {"message_id": str(msg.id), "status": conv.status}


@router.post("/conversations/{conversation_id}/suggest")
def suggest(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """A suggested reply for the staff member who has taken over. Nothing is sent."""
    _require_staff(principal)
    conv = _get_conv(session, conversation_id)
    tenant = _tenant(session)
    blocked = trial_block_reason(session, tenant, datetime.now(UTC))
    if blocked:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "the trial has ended; choose a plan to use the assistant",
        )
    pack = get_pack(tenant.pack_id)
    history = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(30)
        )
    )[::-1]
    result = build_llm().complete(
        task="worker_turn",
        system_stable=pack.system_prompt,
        system_volatile=tenant_facts(tenant)
        + "\n\nA staff member has taken over this conversation. "
        "Draft the reply they could send; they will edit it.",
        messages=build_messages(history),
        tools=None,
        max_tokens=400,
    )
    record_usage(session, tenant, conv.id, "suggest", result)
    return {"suggestion": result.text}


OWNERS = {"owner", "operator"}


@router.get("/contacts/{contact_id}/export")
def export_one(
    contact_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Everything held about one customer, for a subject access request. Owners only."""
    if principal.role not in OWNERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    c = session.get(Contact, contact_id)
    if c is None or c.merged_into is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    tenant = session.get(Tenant, principal.tenant_id)
    assert tenant is not None
    data = export_contact(session, c, get_pack(tenant.pack_id).sensitive_keys)
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="contact.exported",
            subject_table="contacts",
            subject_id=c.id,
            diff={},
        )
    )
    return data


class EraseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(description='Must be "ERASE"')


@router.post("/contacts/{contact_id}/erase")
def erase_one(
    contact_id: uuid.UUID, body: EraseBody, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Delete a customer and everything that names them (right to erasure). Owners only,
    and not while they have a booking still to come."""
    if principal.role not in OWNERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    if body.confirm != "ERASE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "type ERASE to confirm")
    c = session.get(Contact, contact_id)
    if c is None or c.merged_into is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    upcoming = session.scalar(
        select(Appointment.id)
        .where(
            Appointment.contact_id == c.id,
            Appointment.status == "confirmed",
            Appointment.starts_at >= datetime.now(UTC),
        )
        .limit(1)
    )
    if upcoming is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cancel their upcoming booking first, then erase"
        )
    # Messages are append-only for the app role, so erasure runs as the service role with
    # the tenant filter applied inside erase_contact.
    with service_session() as svc:
        counts = erase_contact(
            svc, principal.tenant_id, c.id, f"user:{principal.user_id}", "erasure request"
        )
    return {"erased": counts}
