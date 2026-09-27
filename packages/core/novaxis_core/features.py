"""Model inputs for a booking, computed one way for training and for live scoring.

Why one module: a model trained on inputs computed one way and scored on inputs computed
another way is quietly wrong. `features()` is the only place the inputs are defined;
`packages/ml` (training) and `no_show.py` (live scoring) both call it.

No personal data: no names, phone numbers or free text. Only when, what, how booked, and
the customer's own attendance history. Every input is known *before* the appointment, so
the model never learns from what happened afterwards.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from novaxis_core.models import Appointment, Conversation, Tenant

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NUMERIC = ("lead_days", "hour", "confirmed", "prior_attended", "prior_no_shows")
CATEGORICAL = ("weekday", "service_code", "channel", "pack_id")


@dataclass(frozen=True)
class Booking:
    starts_at: datetime
    booked_at: datetime
    service_code: str
    channel: str
    pack_id: str
    confirmed: bool
    prior_attended: int
    prior_no_shows: int
    timezone: str = "Europe/London"


def features(b: Booking) -> dict[str, Any]:
    local = b.starts_at.astimezone(ZoneInfo(b.timezone))
    lead = (b.starts_at - b.booked_at).total_seconds() / 86400
    return {
        "lead_days": round(min(max(lead, 0.0), 120.0), 3),
        "hour": float(local.hour),
        "confirmed": 1.0 if b.confirmed else 0.0,
        "prior_attended": float(min(b.prior_attended, 20)),
        "prior_no_shows": float(min(b.prior_no_shows, 10)),
        "weekday": WEEKDAYS[local.weekday()],
        "service_code": b.service_code,
        "channel": b.channel or "none",
        "pack_id": b.pack_id,
    }


def bookings_for(session: Session, tenant: Tenant, appts: list[Appointment]) -> list[Booking]:
    """Booking inputs for these appointments of one tenant. The customer's history counts
    only outcomes of *earlier* appointments."""
    if not appts:
        return []
    conv_ids = {a.conversation_id for a in appts if a.conversation_id}
    channels = (
        dict(
            session.execute(
                select(Conversation.id, Conversation.channel).where(Conversation.id.in_(conv_ids))
            ).all()
        )
        if conv_ids
        else {}
    )
    tz = str(tenant.settings.get("timezone") or "Europe/London")
    out: list[Booking] = []
    for a in appts:
        earlier = session.execute(
            select(Appointment.outcome, func.count())
            .where(
                and_(
                    Appointment.tenant_id == tenant.id,
                    Appointment.contact_id == a.contact_id,
                    Appointment.starts_at < a.starts_at,
                    Appointment.outcome.is_not(None),
                )
            )
            .group_by(Appointment.outcome)
        ).all()
        history = {str(o): int(n) for o, n in earlier}
        out.append(
            Booking(
                starts_at=a.starts_at,
                booked_at=a.created_at,
                service_code=a.service_code,
                channel=str(channels.get(a.conversation_id, "none"))
                if a.conversation_id
                else "none",
                pack_id=tenant.pack_id,
                confirmed=a.customer_confirmed_at is not None
                and a.customer_confirmed_at <= a.starts_at,
                prior_attended=history.get("attended", 0),
                prior_no_shows=history.get("no_show", 0),
                timezone=tz,
            )
        )
    return out


@dataclass(frozen=True)
class LabelledRow:
    starts_at: datetime
    features: dict[str, Any]
    no_show: int


def labelled_rows(session: Session, tenant_ids: list[uuid.UUID] | None = None) -> list[LabelledRow]:
    """Every confirmed appointment with a recorded outcome, as training rows, oldest first.
    `session` is a service session (training reads across businesses); the rows carry no
    identifiers."""
    stmt = select(Tenant)
    if tenant_ids is not None:
        stmt = stmt.where(Tenant.id.in_(tenant_ids))
    rows: list[LabelledRow] = []
    for tenant in session.scalars(stmt):
        appts = list(
            session.scalars(
                select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.status == "confirmed",
                    Appointment.outcome.is_not(None),
                )
                .order_by(Appointment.starts_at)
            )
        )
        for a, b in zip(appts, bookings_for(session, tenant, appts), strict=True):
            rows.append(LabelledRow(a.starts_at, features(b), int(a.outcome == "no_show")))
    rows.sort(key=lambda r: r.starts_at)
    return rows
