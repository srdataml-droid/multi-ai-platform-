"""Login helpers for the dashboard.

Local: POST /auth/dev-login mints a dev token for a seeded user (env local or test only).
Production: the web app signs in with Supabase Auth's password grant and sends that JWT;
this route also binds an `email|` pre-registered user to their provider subject on first
login so an owner can add staff by email before they have ever signed in.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal
from novaxis_api.devtoken import mint
from novaxis_core.models import User
from novaxis_core.settings import get_settings
from novaxis_db.session import service_session

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    passcode: str | None = None


def _dev_login_allowed(passcode: str | None) -> bool:
    s = get_settings()
    if s.env in ("local", "test"):
        return True
    return bool(s.demo_passcode) and hmac.compare_digest(passcode or "", s.demo_passcode)


def sign_in_mode() -> str:
    s = get_settings()
    if s.supabase_url and s.supabase_anon_key:
        return "supabase"
    if s.env in ("local", "test"):
        return "dev"
    return "demo" if s.demo_passcode else "none"


@router.post("/dev-login")
def dev_login(body: DevLogin) -> dict[str, Any]:
    s = get_settings()
    if s.env not in ("local", "test") and not s.demo_passcode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available")
    if not _dev_login_allowed(body.passcode):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong passcode")
    with service_session() as s:
        u = s.scalar(select(User).where(User.email == body.email.lower()))
        if u is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user; run make seed")
        return {"token": mint(u.auth_subject), "role": u.role, "email": u.email}


@router.get("/config")
def auth_config() -> dict[str, Any]:
    """What the login page needs to know: dev, demo passcode, or Supabase sign-in."""
    s = get_settings()
    return {
        "mode": sign_in_mode(),
        "supabase_url": s.supabase_url,
        "supabase_anon_key": s.supabase_anon_key,
    }


@router.get("/whoami")
def whoami(principal: CurrentPrincipal) -> dict[str, Any]:
    return {
        "user_id": str(principal.user_id),
        "email": principal.email,
        "role": principal.role,
        "tenant_id": str(principal.tenant_id),
    }
