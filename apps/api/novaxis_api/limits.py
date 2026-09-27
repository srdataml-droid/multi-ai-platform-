"""Rate limits for the public doors (sign-in, sign-up, website chat). Counted in Postgres
so every serverless instance shares one count. Off in local and test runs unless a test
turns them on, so the suite can send as many messages as it needs."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from novaxis_core.security import allow
from novaxis_core.settings import get_settings
from novaxis_db.session import service_session


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(*rules: tuple[str, int, int]) -> None:
    """Each rule is (key, limit, window_seconds). Counts all of them, then refuses if any
    is over, so a refused caller still uses up their allowance."""
    s = get_settings()
    if not s.rate_limits_enabled and s.env in ("local", "test"):
        return
    with service_session() as session:
        ok = [allow(session, key, limit, window) for key, limit, window in rules]
    if not all(ok):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many requests; please wait and try again"
        )
