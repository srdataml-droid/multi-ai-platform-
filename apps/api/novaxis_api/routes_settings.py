"""Tenant settings, staff and the widget snippet. Owners write; staff read."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.actions import ACTIONS, RISK_ORDER
from novaxis_core.models import AuditLog, Tenant, User
from novaxis_core.settings import get_settings
from novaxis_core.tenant_settings import TenantSettings

router = APIRouter(prefix="/settings", tags=["settings"])
WRITERS = {"owner", "operator"}


def _tenant(session: TenantDb) -> Tenant:
    t = session.scalar(select(Tenant))
    assert t is not None
    return t


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
        t.settings = validated.model_dump()
        changes["settings"] = True
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
    return {"id": str(u.id), "email": u.email, "role": u.role}


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
