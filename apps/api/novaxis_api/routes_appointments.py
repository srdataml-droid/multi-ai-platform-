"""Appointments for the schedule page: the list, and recording whether the customer came
(the outcome labels the no-show model learns from, docs/ml.md)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.features import bookings_for, features
from novaxis_core.models import Appointment, AuditLog, Contact, Tenant
from novaxis_core.no_show import model_for

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
def list_appointments(
    principal: CurrentPrincipal,
    session: TenantDb,
    days: int = 14,
    status: str | None = None,
    back: int = 1,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    back = max(0, min(back, 60))
    stmt = select(Appointment).where(
        Appointment.starts_at >= now - timedelta(days=back),
        Appointment.starts_at <= now + timedelta(days=days),
    )
    if status:
        stmt = stmt.where(Appointment.status == status)
    rows = list(session.scalars(stmt.order_by(Appointment.starts_at)))
    contacts = (
        {
            c.id: c
            for c in session.scalars(
                select(Contact).where(Contact.id.in_([r.contact_id for r in rows]))
            )
        }
        if rows
        else {}
    )
    tenant = session.scalar(select(Tenant))
    risks = _risks(session, tenant, rows, now) if tenant else {}
    names = {
        sv.get("code"): sv.get("name")
        for sv in ((tenant.settings.get("services") if tenant else None) or [])
    }
    return {
        "items": [
            {
                "id": str(a.id),
                "starts_at": a.starts_at.isoformat(),
                "ends_at": a.ends_at.isoformat(),
                "service_code": a.service_code,
                "service_name": names.get(a.service_code) or a.service_code.replace("_", " "),
                "customer_confirmed_at": a.customer_confirmed_at.isoformat()
                if a.customer_confirmed_at
                else None,
                "status": a.status,
                "outcome": a.outcome,
                "risk": risks.get(a.id),
                "external_ref": a.external_ref,
                "contact": {
                    "id": str(a.contact_id),
                    "display_name": contacts[a.contact_id].display_name
                    if a.contact_id in contacts
                    else None,
                },
                "conversation_id": str(a.conversation_id) if a.conversation_id else None,
            }
            for a in rows
        ]
    }


def _risks(
    session: TenantDb, tenant: Tenant, rows: list[Appointment], now: datetime
) -> dict[uuid.UUID, dict[str, Any]]:
    """No-show risk for upcoming confirmed bookings, when a model exists (docs/ml.md)."""
    model = model_for(tenant.slug)
    upcoming = [a for a in rows if a.status == "confirmed" and a.starts_at > now]
    if model is None or not upcoming:
        return {}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for a, b in zip(upcoming, bookings_for(session, tenant, upcoming), strict=True):
        r = model.risk(features(b))
        out[a.id] = {"score": r.score, "level": r.level, "reasons": r.reasons}
    return out


STAFF = {"owner", "staff", "operator"}


class OutcomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["attended", "no_show"] | None


@router.post("/{appointment_id}/outcome")
def record_outcome(
    appointment_id: uuid.UUID, body: OutcomeIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Staff say whether the customer came. Only for confirmed bookings whose time has
    started; `null` clears a mistake."""
    if principal.role not in STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    a = session.get(Appointment, appointment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appointment not found")
    if a.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "only confirmed bookings have an outcome")
    if a.starts_at > datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "this appointment has not started yet")
    before = a.outcome
    a.outcome = body.outcome
    a.outcome_at = datetime.now(UTC) if body.outcome else None
    a.outcome_by = principal.user_id if body.outcome else None
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="appointment.outcome",
            subject_table="appointments",
            subject_id=a.id,
            diff={"from": before, "to": body.outcome},
        )
    )
    session.flush()
    return {"id": str(a.id), "outcome": a.outcome}
