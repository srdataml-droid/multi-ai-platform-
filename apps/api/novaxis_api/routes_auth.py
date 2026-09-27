"""Login helpers for the dashboard.

Local: POST /auth/dev-login mints a dev token for a seeded user (env local or test only).
Production: the web app signs in with Supabase Auth's password grant and sends that JWT;
this route also binds an `email|` pre-registered user to their provider subject on first
login so an owner can add staff by email before they have ever signed in.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_api.auth import CurrentPrincipal, _decode
from novaxis_api.devtoken import mint
from novaxis_api.limits import client_ip, enforce
from novaxis_core.models import Tenant, User
from novaxis_core.security import check_code
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
def dev_login(body: DevLogin, request: Request) -> dict[str, Any]:
    """Local: any seeded user. Hosted demo: the shared passcode opens the demo businesses
    only; a business that signed up uses the login code it was given; an operator needs the
    operator passcode. Every failure looks the same, so the form cannot be used to find out
    which emails have accounts."""
    s = get_settings()
    local = s.env in ("local", "test")
    if not local and not (s.demo_passcode or s.operator_passcode):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available")
    email = body.email.strip().lower()
    enforce((f"login:ip:{client_ip(request)}", 30, 900), (f"login:email:{email}", 10, 900))
    with service_session() as session:
        u = session.scalar(select(User).where(User.email == email))
        if u is None:
            if local:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user; run make seed")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or code")
        if not local and not _may_enter(session, u, body.passcode or ""):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or code")
        return {"token": mint(u.auth_subject), "role": u.role, "email": u.email}


def _may_enter(session: Session, u: User, code: str) -> bool:
    s = get_settings()
    if u.role == "operator":
        return bool(s.operator_passcode) and hmac.compare_digest(code, s.operator_passcode)
    if u.login_code_hash:
        return check_code(code, u.login_code_hash)
    tenant = session.get(Tenant, u.tenant_id)
    demo = tenant is not None and tenant.slug.startswith("demo-")
    return demo and bool(s.demo_passcode) and hmac.compare_digest(code, s.demo_passcode)


@router.post("/refresh")
def refresh(principal: CurrentPrincipal, authorization: str = Header()) -> dict[str, Any]:
    """A fresh token for someone already signed in, so a shift is not cut off after eight
    hours. An operator's one-hour entry into a tenant is never extended."""
    if principal.acting:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator entry is not extended")
    if sign_in_mode() == "supabase":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supabase renews its own sessions")
    subject, _, _ = _decode(authorization.split(" ", 1)[1].strip())
    return {"token": mint(subject)}


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
