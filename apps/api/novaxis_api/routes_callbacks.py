"""Public routine enquiries and staff-only callback records.

Reuse contacts, encrypted messages, conversations, proposals and approval audit rows.
A scheduled callback is a manual task, never a calendar booking or an outbound call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_api.limits import client_ip, enforce
from novaxis_api.routes_approvals import DECIDER_ROLES
from novaxis_api.routes_inbound import _origin_allowed
from novaxis_core.gate import GateContext, decide
from novaxis_core.models import ActionProposal, AuditLog, Contact, Conversation, Message, Tenant
from novaxis_db.session import service_session, tenant_session

router = APIRouter(tags=["callbacks"])


class EnquiryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=7, max_length=25, pattern=r"^\+?[0-9 ()-]+$")
    email: str = Field(min_length=3, max_length=120, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    postcode: str = Field(min_length=2, max_length=12)
    service: Literal["Boiler service", "Boiler replacement quote", "Routine plumbing repair"]
    details: str = Field(min_length=1, max_length=1000)
    preferred_window: str = Field(min_length=1, max_length=160)
    consent: Literal[True]


def _public_tenant(slug: str, request: Request) -> Tenant:
    with service_session() as s:
        tenant = s.scalar(select(Tenant).where(Tenant.slug == slug))
        # Explicit opt-in, independent of model/worker settings. No production tenant is
        # silently enrolled merely by deploying this code.
        if tenant is None or not tenant.settings.get("callback_enquiries_enabled"):
            raise HTTPException(404, "enquiries are not enabled for this business")
        if not _origin_allowed(tenant, request.headers.get("origin")):
            raise HTTPException(403, "this website may not submit enquiries")
        s.expunge(tenant)
        return tenant


@router.get("/enquiries/{slug}")
def enquiry_config(slug: str, request: Request) -> dict[str, str]:
    enforce((f"enquiry-config:{client_ip(request)}", 120, 600))
    return {"business_name": _public_tenant(slug, request).name}


@router.post("/enquiries/{slug}", status_code=201)
def submit(slug: str, body: EnquiryIn, request: Request) -> dict[str, bool]:
    enforce(
        (f"enquiry-ip:{client_ip(request)}", 10, 600),
        (f"enquiry-tenant:{slug}", 100, 3600),
    )
    tenant = _public_tenant(slug, request)
    ref = f"enquiry:{body.request_id}"
    with tenant_session(tenant.id) as s:
        # Serialise retries across instances, without a process-local cache. Never return
        # existing customer data from this unauthenticated endpoint.
        s.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"{tenant.id}:{ref}"},
        )
        if s.scalar(select(Message.id).where(Message.provider_ref == ref)):
            return {"received": True}
        contact = Contact(
            tenant_id=tenant.id,
            display_name=body.name,
            phones=[body.phone],
            emails=[body.email],
            consent={"status": "opted_in", "scope": "requested_callback"},
        )
        s.add(contact)
        s.flush()
        conv = Conversation(
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel="webchat",
            status="waiting_human",
            summary=body.details,
            extracted={"postcode": body.postcode, "service": body.service},
        )
        s.add(conv)
        s.flush()
        s.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                channel="webchat",
                direction="inbound",
                author="customer",
                body=body.details,
                provider_ref=ref,
            )
        )
        params = {"window": body.preferred_window}
        gate = decide("schedule_callback", params, GateContext(tenant_settings=tenant.settings))
        proposal = ActionProposal(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            kind="schedule_callback",
            params=params,
            risk=gate.risk,
            state=gate.state,
            reason=gate.reason,
        )
        s.add(proposal)
        s.flush()
        s.add(
            AuditLog(
                tenant_id=tenant.id,
                actor="visitor:enquiry",
                event="callback.requested",
                subject_table="action_proposals",
                subject_id=proposal.id,
                diff={"source": "website_form"},
            )
        )
    return {"received": True}


def _record(s: TenantDb, p: ActionProposal) -> dict[str, Any]:
    conv = s.get(Conversation, p.conversation_id)
    contact = s.get(Contact, conv.contact_id) if conv else None
    return {
        "id": str(p.id),
        "state": p.state,
        "window": p.params.get("window", ""),
        "outcome": (p.result or {}).get("outcome"),
        "created_at": p.created_at.isoformat(),
        "name": contact.display_name if contact else "",
        "phone": contact.phones[0] if contact and contact.phones else "",
        "email": contact.emails[0] if contact and contact.emails else "",
        "details": conv.summary if conv else "",
        "intake": conv.extracted if conv else {},
    }


@router.get("/callbacks")
def callbacks(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(403, "callback records require a reviewer role")
    rows = session.scalars(
        select(ActionProposal)
        .where(ActionProposal.kind == "schedule_callback", ActionProposal.superseded_by.is_(None))
        .order_by(ActionProposal.created_at.desc())
        .limit(100)
    )
    return {"items": [_record(session, p) for p in rows]}


class OutcomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["completed", "no_answer", "cancelled"]


@router.post("/callbacks/{proposal_id}/outcome")
def outcome(
    proposal_id: uuid.UUID, body: OutcomeIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(403, "viewers cannot record callback outcomes")
    p = session.scalar(
        select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
    )
    if p is None or p.kind != "schedule_callback":
        raise HTTPException(404, "no such callback")
    if p.state != "executed" or (p.result or {}).get("outcome") != "scheduled":
        raise HTTPException(409, "callback is not awaiting an outcome")
    p.result = {
        **(p.result or {}),
        "outcome": body.outcome,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    session.add(
        AuditLog(
            tenant_id=p.tenant_id,
            actor=f"user:{principal.user_id}",
            event="callback.outcome",
            subject_table="action_proposals",
            subject_id=p.id,
            diff={"outcome": body.outcome},
        )
    )
    return _record(session, p)


class CallbackConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("/callbacks/config")
def callback_config(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    if principal.role not in DECIDER_ROLES:
        raise HTTPException(403, "reviewer role required")
    tenant = session.get(Tenant, principal.tenant_id)
    assert tenant is not None
    return {
        "enabled": bool(tenant.settings.get("callback_enquiries_enabled")),
        "slug": tenant.slug,
        "can_configure": principal.role in {"owner", "operator"},
    }


@router.put("/callbacks/config")
def configure(
    body: CallbackConfigIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    if principal.role not in {"owner", "operator"}:
        raise HTTPException(403, "only owners can enable enquiries")
    tenant = session.scalar(
        select(Tenant).where(Tenant.id == principal.tenant_id).with_for_update()
    )
    assert tenant is not None
    tenant.settings = {**tenant.settings, "callback_enquiries_enabled": body.enabled}
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor=f"user:{principal.user_id}",
            event="callback.configuration",
            subject_table="tenants",
            subject_id=tenant.id,
            diff={"enabled": body.enabled},
        )
    )
    return {"enabled": body.enabled}
