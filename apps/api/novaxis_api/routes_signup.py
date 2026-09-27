"""Self-serve sign-up: a new business gets a tenant, an owner login and a trial.

Who may sign up depends on the deployment's sign-in mode (routes_auth.py):
- supabase: the caller has just created a Supabase Auth account and sends its JWT;
- demo: the caller knows the demo passcode;
- local and test: anyone.
A cap on tenant count stops a leaked demo passcode from filling the database.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_api.auth import _decode
from novaxis_api.devtoken import mint
from novaxis_api.limits import client_ip, enforce
from novaxis_api.routes_auth import _dev_login_allowed, sign_in_mode
from novaxis_core.billing import start_trial
from novaxis_core.models import AuditLog, Location, Tenant, User
from novaxis_core.security import hash_code, new_login_code
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import TenantSettings
from novaxis_db.session import service_session
from novaxis_packs import available_packs, get_pack

router = APIRouter(prefix="/signup", tags=["signup"])


@router.get("/options")
def options() -> dict[str, Any]:
    s = get_settings()
    return {
        "mode": sign_in_mode(),
        "trial_days": s.trial_days,
        "trial_reply_cap": s.trial_message_cap,
        "packs": [{"id": p, "name": get_pack(p).name} for p in available_packs() if p != "generic"]
        + [{"id": "generic", "name": get_pack("generic").name}],
    }


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_name: str = Field(min_length=2, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    pack_id: str
    passcode: str | None = None


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "business"
    if base.startswith("demo-") or base == "novaxis-ops":
        base = "biz-" + base
    return base


def _unique_slug(session: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    while session.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


@router.post("")
def signup(
    body: SignupIn, request: Request, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    s = get_settings()
    mode = sign_in_mode()
    enforce((f"signup:ip:{client_ip(request)}", 5, 3600))
    email = body.email.lower()
    subject: str
    if mode == "supabase":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "create your account first")
        subject, token_email, _ = _decode(authorization.split(" ", 1)[1].strip())
        if token_email and token_email != email:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "email does not match")
    elif mode == "none":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sign-up is not available here")
    else:
        if not _dev_login_allowed(body.passcode):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong passcode")
        subject = f"email|{email}"
    if body.pack_id not in available_packs():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown pack")

    # Hosted demo: the business gets its own login code, shown once. The shared demo
    # passcode never opens a real sign-up's account.
    login_code = new_login_code()
    with service_session() as session:
        customers = session.scalar(
            select(func.count()).select_from(Tenant).where(Tenant.plan != "internal")
        )
        if (customers or 0) >= s.signup_max_tenants:
            raise HTTPException(status.HTTP_409_CONFLICT, "sign-up is full on this deployment")
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "that email already has an account")
        if session.scalar(select(User.id).where(User.auth_subject == subject)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "that login already has an account")
        now = datetime.now(UTC)
        tenant = Tenant(
            name=body.business_name.strip(),
            slug=_unique_slug(session, body.business_name),
            pack_id=body.pack_id,
            settings=TenantSettings(pack_id=body.pack_id).model_dump(),
        )
        start_trial(tenant, now)
        session.add(tenant)
        session.flush()
        session.add(Location(tenant_id=tenant.id, name="Main", timezone="Europe/London"))
        owner = User(
            tenant_id=tenant.id,
            auth_subject=subject,
            email=email,
            role="owner",
            display_name=None,
            login_code_hash=hash_code(login_code) if mode == "demo" else None,
        )
        session.add(owner)
        session.flush()
        session.add(
            AuditLog(
                tenant_id=tenant.id,
                actor=f"user:{owner.id}",
                event="tenant.created",
                subject_table="tenants",
                subject_id=tenant.id,
                diff={"pack_id": body.pack_id, "via": mode},
            )
        )
        tenant_id: uuid.UUID = tenant.id
        slug = tenant.slug
    return {
        "tenant_id": str(tenant_id),
        "slug": slug,
        # Supabase callers already hold their token; everyone else gets one here.
        "token": None if mode == "supabase" else mint(subject),
        "login_code": login_code if mode == "demo" else None,
    }
