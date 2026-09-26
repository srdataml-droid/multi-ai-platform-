"""Write one audit row. Application code calls this at every state change
(ADR 0004: application-level audit, not triggers)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.models import AuditLog


def record(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    event: str,
    subject_table: str | None = None,
    subject_id: uuid.UUID | None = None,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        event=event,
        subject_table=subject_table,
        subject_id=subject_id,
        diff=diff or {},
    )
    session.add(row)
    session.flush()
    return row
