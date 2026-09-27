"""GET /health/deep: is the service actually working, not just answering?

Public on purpose, so a free scheduled check (GitHub Actions, .github/workflows/monitor.yml)
can call it and email the founder when it fails. It returns yes/no answers and counts only,
never tenant data, and answers 503 when anything needs a person.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func, select, text

from novaxis_api.limits import client_ip, enforce
from novaxis_core.models import ActionProposal, Job, Tenant
from novaxis_core.settings import get_settings
from novaxis_db import migrate
from novaxis_db.session import normalise_url, service_session

router = APIRouter(tags=["health"])


@router.get("/health/deep")
def deep(request: Request, response: Response) -> dict[str, Any]:
    enforce((f"health:ip:{client_ip(request)}", 60, 600))
    now = datetime.now(UTC)
    checks: dict[str, Any] = {}
    try:
        with service_session() as s:
            s.execute(text("select 1"))
            checks["database"] = True
            # Only jobs the worker should be taking: paused, closed or switched-off businesses
            # keep their queue on purpose.
            checks["stuck_jobs"] = int(
                s.scalar(
                    select(func.count())
                    .select_from(Job)
                    .join(Tenant, Tenant.id == Job.tenant_id)
                    .where(
                        Job.state == "queued",
                        Job.run_after < now - timedelta(minutes=15),
                        Tenant.worker_enabled.is_(True),
                        Tenant.status.in_(["active", "trial"]),
                    )
                )
                or 0
            )
            checks["failed_jobs_last_hour"] = int(
                s.scalar(
                    select(func.count()).where(
                        Job.state == "failed", Job.created_at > now - timedelta(hours=1)
                    )
                )
                or 0
            )
            checks["emergency_alerts_not_delivered_24h"] = int(
                s.scalar(
                    select(func.count()).where(
                        ActionProposal.kind == "escalate_emergency",
                        ActionProposal.state == "failed",
                        ActionProposal.created_at > now - timedelta(hours=24),
                    )
                )
                or 0
            )
        url = normalise_url(get_settings().database_url)
        checks["schema_current"] = migrate.current(url) == migrate.head(url)
    except Exception as exc:  # noqa: BLE001 - the whole point is to report, not to crash
        checks["database"] = checks.get("database", False)
        checks["error"] = type(exc).__name__
    ok = (
        checks.get("database") is True
        and checks.get("schema_current") is True
        and checks.get("stuck_jobs", 1) == 0
        and checks.get("emergency_alerts_not_delivered_24h", 1) == 0
    )
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ok": ok, "checks": checks, "at": now.isoformat()}
