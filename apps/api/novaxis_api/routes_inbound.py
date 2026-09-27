"""Inbound webhooks. Verify, parse, route to a tenant, ingest, answer fast.

Every route does the same five steps and returns the shape its provider expects.
Nothing here calls an LLM; that is the worker's job (Chunk 3).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from novaxis_api.limits import client_ip, enforce
from novaxis_core.channels import InboundRequest, NormalisedInbound, ParseError, get_adapter
from novaxis_core.channels.webchat import mint_visitor_token, verify_visitor_token
from novaxis_core.channels.whatsapp import verify_handshake
from novaxis_core.inbound import IngestResult, ingest
from novaxis_core.models import Contact, Conversation, Message, Tenant
from novaxis_core.routing import resolve_tenant
from novaxis_core.settings import get_settings
from novaxis_db.session import service_session, tenant_session

log = logging.getLogger("novaxis.inbound")
router = APIRouter(prefix="/inbound", tags=["inbound"])


async def _to_inbound_request(request: Request) -> InboundRequest:
    form: dict[str, str] = {}
    body_json: dict[str, Any] | None = None
    raw = await request.body()
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        parsed = await request.json()
        body_json = parsed if isinstance(parsed, dict) else {}
    elif "form" in ctype:
        form = {k: str(v) for k, v in (await request.form()).items()}
    return InboundRequest(
        url=str(request.url),
        headers=dict(request.headers),
        form=form,
        json=body_json,
        query=dict(request.query_params),
        raw_body=raw,
    )


def _verify_and_parse(channel: str, req: InboundRequest) -> NormalisedInbound:
    adapter = get_adapter(channel)
    if not adapter.verify_signature(req):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad signature")
    try:
        return adapter.parse_inbound(req)
    except ParseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _route_and_ingest(inbound: NormalisedInbound) -> tuple[Tenant, IngestResult]:
    with service_session() as s:
        tenant = resolve_tenant(s, inbound.channel, inbound.tenant_ref)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no tenant for this destination")
        channel_cfg = (tenant.settings.get("channels") or {}).get(inbound.channel) or {}
        if not channel_cfg.get("enabled"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not enabled for tenant")
        s.expunge(tenant)
    with tenant_session(tenant.id) as ts:
        result = ingest(ts, tenant, inbound)
    log.info(
        "inbound %s tenant=%s conversation=%s duplicate=%s opted_out=%s",
        inbound.channel,
        tenant.slug,
        result.conversation_id,
        result.duplicate,
        result.opted_out,
    )
    return tenant, result


def _origin_allowed(tenant: Tenant, origin: str | None) -> bool:
    """A business can list the websites allowed to host its widget. Our own dashboard (the
    demo page, the widget preview) is always allowed; no Origin header means not a browser."""
    allowed = tenant.settings.get("widget_origins") or []
    if not allowed or not origin:
        return True
    origin = origin.rstrip("/").lower()
    own = get_settings().public_web_url.rstrip("/").lower()
    return origin == own or origin in allowed


def _check_widget(tenant_slug: str, request: Request, visitor: str | None) -> None:
    ip = client_ip(request)
    rules = [(f"chat:ip:{ip}", 30, 600), (f"chat:tenant:{tenant_slug}", 600, 3600)]
    if visitor:
        rules.append((f"chat:visitor:{visitor}", 20, 600))
    enforce(*rules)
    with service_session() as s:
        tenant = resolve_tenant(s, "webchat", tenant_slug)
        if tenant is not None and not _origin_allowed(tenant, request.headers.get("origin")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "this website may not use the widget")


@router.post("/webchat/{tenant_slug}")
async def webchat(tenant_slug: str, request: Request) -> dict[str, Any]:
    req = await _to_inbound_request(request)
    token = (req.json or {}).get("visitor_token")
    _check_widget(tenant_slug, request, verify_visitor_token(token) if token else None)
    req = InboundRequest(
        url=req.url,
        headers=req.headers,
        form=req.form,
        json=req.json,
        query={"tenant": tenant_slug},
    )
    inbound = _verify_and_parse("webchat", req)
    _, result = _route_and_ingest(inbound)
    assert inbound.sender_visitor_id is not None
    return {
        "conversation_id": str(result.conversation_id),
        "message_id": str(result.message_id),
        "visitor_token": mint_visitor_token(inbound.sender_visitor_id),
        "duplicate": result.duplicate,
    }


@router.get("/webchat/{tenant_slug}/messages")
def webchat_messages(
    tenant_slug: str, visitor_token: str, request: Request, after: str | None = None
) -> dict[str, Any]:
    """The widget polls this for replies. Only the visitor's own conversation is readable,
    because the visitor id comes from a token we signed."""
    visitor_id = verify_visitor_token(visitor_token)
    if visitor_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad visitor token")
    # Polling every 3 s while open is 200 per 10 minutes; allow a little over that.
    enforce((f"poll:visitor:{visitor_id}", 300, 600))
    with service_session() as s:
        tenant = resolve_tenant(s, "webchat", tenant_slug)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
        tenant_id = tenant.id
    with tenant_session(tenant_id) as ts:
        contact = ts.scalar(select(Contact).where(Contact.visitor_ids.contains([visitor_id])))
        if contact is None:
            return {"messages": []}
        conv = ts.scalar(
            select(Conversation)
            .where(Conversation.contact_id == contact.id, Conversation.channel == "webchat")
            .order_by(Conversation.created_at.desc())
        )
        if conv is None:
            return {"messages": []}
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
        )
        rows = list(ts.scalars(stmt))
        if after:
            seen = {str(m.id) for m in rows}
            if after in seen:
                idx = [str(m.id) for m in rows].index(after)
                rows = rows[idx + 1 :]
        return {
            "conversation_id": str(conv.id),
            "status": conv.status,
            "messages": [
                {
                    "id": str(m.id),
                    "direction": m.direction,
                    "author": m.author,
                    "body": m.body,
                    "at": m.created_at.isoformat(),
                }
                for m in rows
            ],
        }


@router.post("/twilio/sms")
async def twilio_sms(request: Request) -> Response:
    req = await _to_inbound_request(request)
    inbound = _verify_and_parse("twilio_sms", req)
    _route_and_ingest(inbound)
    # Empty TwiML: we reply asynchronously through the API, never inline.
    return Response(content="<Response></Response>", media_type="text/xml")


@router.post("/email/postmark")
async def email_postmark(request: Request) -> dict[str, Any]:
    req = await _to_inbound_request(request)
    inbound = _verify_and_parse("email", req)
    _, result = _route_and_ingest(inbound)
    return {"ok": True, "duplicate": result.duplicate}


@router.get("/whatsapp")
def whatsapp_handshake(request: Request) -> Response:
    """Meta's one-off subscription check when the webhook is set up."""
    challenge = verify_handshake(dict(request.query_params))
    if challenge is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verify token does not match")
    return Response(content=challenge, media_type="text/plain")


@router.post("/whatsapp")
async def whatsapp(request: Request) -> dict[str, Any]:
    """One POST can hold several messages, or only delivery receipts (ignored). Meta retries
    anything that is not a 200, so every message is ingested idempotently by its id, and a
    message for a business that has not enabled WhatsApp is dropped with a log line, not an
    error that would make Meta retry for days."""
    req = await _to_inbound_request(request)
    adapter = get_adapter("whatsapp")
    if not adapter.verify_signature(req):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad signature")
    try:
        messages = adapter.parse_many(req)  # type: ignore[attr-defined]
    except ParseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    taken = 0
    for inbound in messages:
        try:
            _route_and_ingest(inbound)
            taken += 1
        except HTTPException as exc:
            log.warning("whatsapp message %s dropped: %s", inbound.provider_ref, exc.detail)
    return {"ok": True, "messages": len(messages), "ingested": taken}
