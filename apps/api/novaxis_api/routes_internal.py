"""Operator endpoints for serverless hosting, protected by NOVAXIS_CRON_SECRET.

- POST /internal/tick     run scheduled work (roll-ups, follow-ups, reminders). A timer calls it.
- POST /internal/migrate  apply database migrations (alembic upgrade head).
- POST /internal/seed     create or refresh the demo tenants.
- POST /internal/rekey    move encrypted data to NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT, a pass at
                          a time; call until "remaining" is 0 (docs/encryption.md).

With no secret configured these return 404, so a local or misconfigured deployment
exposes nothing.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from novaxis_api.inline_worker import drain_for
from novaxis_core.settings import get_settings
from novaxis_db import migrate
from novaxis_db.rekey import rekey
from novaxis_db.seed import seed
from novaxis_db.session import service_session

router = APIRouter(prefix="/internal", tags=["internal"])


def _check(authorization: str | None) -> None:
    secret = get_settings().cron_secret
    if not secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad secret")


@router.post("/tick")
@router.get("/tick")
def internal_tick(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check(authorization)
    try:
        return {"jobs_run": drain_for(budget_seconds=40, raise_errors=True)}
    except Exception as exc:  # noqa: BLE001 - the timer must see a failure as a failure
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"tick failed: {type(exc).__name__}"
        ) from exc


@router.post("/migrate")
def internal_migrate(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check(authorization)
    migrate.upgrade(get_settings().database_url, "head")
    return {"ok": True}


@router.post("/seed")
def internal_seed(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check(authorization)
    with service_session() as s:
        tenants = seed(s)
        return {"tenants": [t.slug for t in tenants]}


@router.post("/rekey")
def internal_rekey(
    authorization: str | None = Header(default=None), budget: int = 2000
) -> dict[str, Any]:
    _check(authorization)
    if not get_settings().sensitive_fields_key_next.strip():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "set NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT and redeploy first"
        )
    with service_session() as s:
        return rekey(s, budget=max(1, min(budget, 5000)))
