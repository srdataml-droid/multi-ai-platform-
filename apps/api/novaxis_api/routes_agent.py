"""The agent API: a business's own agent (e.g. one built with Hermes) reads conversations
and proposes actions; the platform's approval gate decides. Rules in novaxis_core/agent.py,
guide in docs/agent-api.md.

/agent/v1/*         for the agent, with an agent key (`Authorization: Bearer nvx_agent_...`)
/settings/agent-keys for the owner, with their normal sign-in: create, list, revoke keys

Agent keys work only on /agent/v1, and sign-in tokens do not work there: an agent cannot
approve its own proposals or change settings, by construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_api.limits import enforce
from novaxis_core.agent import (
    AgentError,
    agent_propose,
    context,
    find_key,
    new_key,
    openai_tools,
    proposal_view,
    waiting,
)
from novaxis_core.agent_webhooks import WebhookError, ping, set_webhook
from novaxis_core.billing import trial_block_reason
from novaxis_core.models import ActionProposal, AgentKey, AuditLog, Conversation, Tenant
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

router = APIRouter(prefix="/agent/v1", tags=["agent"])
keys_router = APIRouter(prefix="/settings/agent-keys", tags=["settings"])

KEY_OWNERS = {"owner", "operator"}


@dataclass(frozen=True)
class AgentCaller:
    key_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str


def agent_caller(authorization: str | None = Header(default=None)) -> AgentCaller:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing agent key")
    key = authorization.split(" ", 1)[1].strip()
    # The key decides the tenant: the one lookup that needs the service session.
    with service_session() as s:
        row = find_key(s, key)
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or revoked agent key")
        now = datetime.now(UTC)
        if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=1):
            row.last_used_at = now
        caller = AgentCaller(row.id, row.tenant_id, row.name)
    enforce((f"agent:{caller.key_id}", 600, 60))
    return caller


Caller = Annotated[AgentCaller, Depends(agent_caller)]


def agent_db(caller: Caller) -> Iterator[Session]:
    with tenant_session(caller.tenant_id) as s:
        yield s


AgentDb = Annotated[Session, Depends(agent_db)]


def _tenant(session: Session) -> Tenant:
    t = session.scalar(select(Tenant))
    assert t is not None
    return t


def _conversation(session: Session, conversation_id: uuid.UUID) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such conversation")
    return conv


@router.get("/tools")
def tools(caller: Caller, session: AgentDb) -> dict[str, Any]:
    """The tools this business's agent may propose, in OpenAI function-calling format, and
    the instructions the built-in assistant follows, so an agent can start from the same."""
    t = _tenant(session)
    pack = get_pack(t.pack_id)
    return {
        "business": t.name,
        "assistant": t.settings.get("assistant", "built_in"),
        "instructions": pack.system_prompt,
        "tools": openai_tools(pack),
    }


@router.get("/conversations")
def conversations(caller: Caller, session: AgentDb) -> dict[str, Any]:
    """Conversations where the customer is waiting for an answer."""
    items = waiting(session)
    return {"items": items, "count": len(items)}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: uuid.UUID, caller: Caller, session: AgentDb) -> dict[str, Any]:
    t = _tenant(session)
    return context(session, t, get_pack(t.pack_id), _conversation(session, conversation_id))


class ProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=60)
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/conversations/{conversation_id}/proposals")
def propose(
    conversation_id: uuid.UUID,
    body: ProposalIn,
    caller: Caller,
    session: AgentDb,
    response: Response,
) -> dict[str, Any]:
    """Propose one action. The gate decides: `executed` (low risk, done), `awaiting` (staff
    decide; poll GET /proposals/{id}), or `rejected` (with the reason)."""
    t = _tenant(session)
    if t.settings.get("assistant") != "external":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this business uses the built-in assistant; the owner must set Settings > "
            "'Who answers customers' to 'Our own agent' first, so customers never get two replies",
        )
    blocked = trial_block_reason(session, t, datetime.now(UTC))
    if blocked:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, blocked)
    conv = _conversation(session, conversation_id)
    key = session.get(AgentKey, caller.key_id)
    assert key is not None
    try:
        p, created = agent_propose(
            session, t, get_pack(t.pack_id), conv, key, body.kind, body.params
        )
    except AgentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {**proposal_view(p), "duplicate": not created}


@router.get("/proposals/{proposal_id}")
def proposal(proposal_id: uuid.UUID, caller: Caller, session: AgentDb) -> dict[str, Any]:
    p = session.get(ActionProposal, proposal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such proposal")
    return proposal_view(p)


# --- the owner's side ----------------------------------------------------------------------


def _require_owner(principal: CurrentPrincipal) -> None:
    if principal.role not in KEY_OWNERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can manage agent keys")


def _key_view(k: AgentKey) -> dict[str, Any]:
    return {
        "id": str(k.id),
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at.isoformat(),
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "webhook_url": k.webhook_url,
    }


@keys_router.get("")
def list_keys(principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _require_owner(principal)
    rows = session.scalars(select(AgentKey).order_by(AgentKey.created_at.desc()))
    return {"items": [_key_view(k) for k in rows]}


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


@keys_router.post("", status_code=status.HTTP_201_CREATED)
def create_key(body: KeyIn, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    """The key is in this response and nowhere else: we keep only its hash."""
    _require_owner(principal)
    row, key = new_key(session, principal.tenant_id, body.name, principal.user_id)
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="agent_key.created",
            subject_table="agent_keys",
            subject_id=row.id,
            diff={"name": row.name, "prefix": row.prefix},
        )
    )
    return {**_key_view(row), "key": key}


@keys_router.delete("/{key_id}")
def revoke_key(key_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb) -> dict[str, Any]:
    _require_owner(principal)
    row = session.get(AgentKey, key_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                actor=f"user:{principal.user_id}",
                event="agent_key.revoked",
                subject_table="agent_keys",
                subject_id=row.id,
                diff={"name": row.name},
            )
        )
    session.flush()
    return _key_view(row)


def _active_key(session: TenantDb, key_id: uuid.UUID) -> AgentKey:
    row = session.get(AgentKey, key_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    if row.revoked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this key is revoked")
    return row


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str | None = Field(default=None, max_length=500)


@keys_router.put("/{key_id}/webhook")
def put_webhook(
    key_id: uuid.UUID, body: WebhookIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Set (or clear, with no url) where events are pushed. Setting it makes a new signing
    secret, in this response only."""
    _require_owner(principal)
    row = _active_key(session, key_id)
    try:
        secret = set_webhook(row, body.url)
    except WebhookError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="agent_key.webhook_set" if secret else "agent_key.webhook_cleared",
            subject_table="agent_keys",
            subject_id=row.id,
            diff={"url": row.webhook_url or ""},
        )
    )
    session.flush()
    return {**_key_view(row), **({"webhook_secret": secret} if secret else {})}


@keys_router.post("/{key_id}/webhook/test")
def send_test_event(
    key_id: uuid.UUID, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Send a signed `ping` now and say what the agent answered."""
    _require_owner(principal)
    row = _active_key(session, key_id)
    try:
        code = ping(row)
    except (WebhookError, httpx.HTTPError) as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}
    return {"ok": True, "status_code": code}
