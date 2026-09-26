"""Read appointments for the schedule page (Chunk 9) and for tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.models import Appointment, Contact

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
def list_appointments(
    principal: CurrentPrincipal, session: TenantDb, days: int = 14, status: str | None = None
) -> dict[str, Any]:
    now = datetime.now(UTC)
    stmt = select(Appointment).where(
        Appointment.starts_at >= now - timedelta(days=1),
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
    return {
        "items": [
            {
                "id": str(a.id),
                "starts_at": a.starts_at.isoformat(),
                "ends_at": a.ends_at.isoformat(),
                "service_code": a.service_code,
                "status": a.status,
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
