"""Tenant settings, staff and the widget snippet. Owners write; staff read."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_api.routes_auth import sign_in_mode
from novaxis_core.actions import ACTIONS, RISK_ORDER
from novaxis_core.assistant_templates import template_for
from novaxis_core.booking_types import encrypt_existing, sensitive_keys_for, starter_type
from novaxis_core.models import AuditLog, Location, Tenant, UsageEvent, User
from novaxis_core.pack_registry import resolve_pack
from novaxis_core.routing import claim_error, keep_routing
from novaxis_core.security import hash_code, new_login_code
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import TenantSettings

router = APIRouter(prefix="/settings", tags=["settings"])
WRITERS = {"owner", "operator"}


def _tenant(session: TenantDb) -> Tenant:
    t = session.scalar(select(Tenant))
    assert t is not None
    return t


def save_or_409(session: TenantDb) -> None:
    """Write now, so a clash over a routing address (SMS number, inbound email) becomes a
    readable 409 instead of a server error."""
    try:
        session.flush()
    except IntegrityError as exc:
        reason = claim_error(exc)
        if reason is None:
            raise
        raise HTTPException(status.HTTP_409_CONFLICT, reason) from exc


def _require_owner(principal: CurrentPrincipal) -> None:
    if principal.role not in WRITERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can change settings")


@router.get("")
def read_settings(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    t = _tenant(session)
    return {
        "tenant": {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "pack_id": t.pack_id,
            "status": t.status,
            "worker_enabled": t.worker_enabled,
        },
        "settings": t.settings,
        "risk_floors": {
            k: {"default": a.default_risk, "floor": a.floor, "description": a.description}
            for k, a in ACTIONS.items()
        },
        # The trade's standard questions as a booking type, for "Start from our standard
        # questions" in Settings > Booking types.
        "starter_booking_type": starter_type(
            resolve_pack(t.pack_id), list(t.settings.get("services") or [])
        ),
    }


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    worker_enabled: bool | None = None
    settings: dict[str, Any] | None = None


@router.put("")
def write_settings(
    body: SettingsIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    _require_owner(principal)
    t = _tenant(session)
    changes: dict[str, Any] = {}
    if body.settings is not None:
        try:
            validated = TenantSettings.model_validate(body.settings)
        except ValidationError as exc:
            first = exc.errors()[0]
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{'.'.join(str(x) for x in first['loc'])}: {first['msg']}",
            ) from exc
        if validated.pack_id != t.pack_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "pack_id cannot be changed here"
            )
        for kind, risk in validated.risk_overrides.items():
            if kind not in ACTIONS:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"risk_overrides: unknown action {kind}"
                )
            if RISK_ORDER[risk] < RISK_ORDER[ACTIONS[kind].floor]:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"risk_overrides.{kind}: cannot go below {ACTIONS[kind].floor}",
                )
        saved = validated.model_dump()
        if principal.role != "operator":
            # The SMS number and inbound address route other people's messages here; an
            # owner sets the number in onboarding, and the inbound address is fixed.
            saved = keep_routing(saved, t.settings)
        pack = resolve_pack(t.pack_id)
        was_private = sensitive_keys_for(t, pack)
        t.settings = saved
        save_or_409(session)
        changes["settings"] = True
        # Answers already stored under a question just marked Private are encrypted now,
        # not only the ones that arrive from here on.
        newly = sensitive_keys_for(t, pack) - was_private
        if newly:
            changes["encrypted_existing"] = encrypt_existing(session, newly)
        # Slots are computed in the location's time zone; keep it in step with settings.
        for loc in session.scalars(select(Location)):
            loc.timezone = validated.timezone
    if body.name is not None:
        t.name = body.name
        changes["name"] = body.name
    if body.worker_enabled is not None:
        t.worker_enabled = body.worker_enabled
        changes["worker_enabled"] = body.worker_enabled
    session.add(
        AuditLog(
            tenant_id=t.id,
            actor=f"user:{principal.user_id}",
            event="settings.updated",
            subject_table="tenants",
            subject_id=t.id,
            diff=changes,
        )
    )
    session.flush()
    return read_settings(principal, session)


@router.get("/staff")
def list_staff(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    rows = list(session.scalars(select(User).order_by(User.created_at)))
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "display_name": u.display_name,
                "created_at": u.created_at.isoformat(),
            }
            for u in rows
        ]
    }


class StaffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    role: str
    display_name: str | None = None


@router.post("/staff")
def add_staff(body: StaffIn, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    """Pre-registers a user by email. Their identity provider subject is bound on first login
    (Supabase: the email claim matches). Until then the row carries an email-based subject."""
    _require_owner(principal)
    if body.role not in ("owner", "staff", "viewer"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "role must be owner, staff or viewer"
        )
    email = body.email.lower()
    if session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that email is already a member")
    u = User(
        tenant_id=principal.tenant_id,
        auth_subject=f"email|{email}",
        email=email,
        role=body.role,
        display_name=body.display_name,
    )
    # Hosted without an identity provider, a member signs in with email and a code of
    # their own, shown to the owner once to pass on (as a new business gets at sign-up).
    code = new_login_code() if sign_in_mode() == "demo" else None
    if code:
        u.login_code_hash = hash_code(code)
    session.add(u)
    session.flush()
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="staff.added",
            subject_table="users",
            subject_id=u.id,
            diff={"role": body.role},
        )
    )
    return {"id": str(u.id), "email": u.email, "role": u.role, "login_code": code}


@router.post("/staff/{user_id}/code")
def new_code(user_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    """A lost code: the owner issues a new one and the old one stops working."""
    _require_owner(principal)
    if sign_in_mode() != "demo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sign-in codes are not used here")
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    code = new_login_code()
    u.login_code_hash = hash_code(code)
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="staff.code_reset",
            subject_table="users",
            subject_id=u.id,
            diff={},
        )
    )
    return {"id": str(u.id), "login_code": code}


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str


@router.put("/staff/{user_id}")
def set_role(
    user_id: uuid.UUID, body: RoleIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    _require_owner(principal)
    if body.role not in ("owner", "staff", "viewer"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "role must be owner, staff or viewer"
        )
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    if u.id == principal.user_id and body.role != "owner":
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot demote yourself")
    u.role = body.role
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="staff.role_changed",
            subject_table="users",
            subject_id=u.id,
            diff={"role": body.role},
        )
    )
    return {"id": str(u.id), "role": u.role}


@router.get("/widget")
def widget_snippet(principal: CurrentPrincipal, session: TenantDb) -> dict[str, str]:
    t = _tenant(session)
    s = get_settings()
    web = s.public_web_url or "https://YOUR-DASHBOARD-HOST"
    return {
        "snippet": (
            f'<script src="{web}/widget.js" data-tenant="{t.slug}" '
            f'data-api="{s.public_base_url}"></script>'
        ),
        "tenant": t.slug,
    }


@router.get("/assistant")
def assistant_configuration(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    """Safe model metadata, with observed worker usage kept distinct from API config."""
    _require_owner(principal)
    s = get_settings()
    recent = session.scalar(
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == principal.tenant_id,
            UsageEvent.kind == "llm.worker_turn",
            UsageEvent.model.is_not(None),
        )
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(1)
    )
    scripted = s.llm_provider == "fake"
    return {
        "provider": s.llm_provider,
        "scripted": scripted,
        "models": {
            "responses": "fake" if scripted else s.model_worker,
            "classification": "fake" if scripted else s.model_classify,
            "summaries": "fake" if scripted else s.model_summarise,
        },
        "configuration_scope": "api_process",
        "latest_worker_call": None if recent is None else {
            "model": recent.model,
            "at": recent.created_at.isoformat(),
        },
    }


@router.get("/assistant-template")
def read_assistant_template(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _require_owner(principal)
    t = _tenant(session)
    return template_for(t.pack_id)
