"""Inbound webhooks. Verify, parse, route to a tenant, ingest, answer fast.

Every route does the same five steps and returns the shape its provider expects.
Nothing here calls an LLM; that is the worker's job (Chunk 3).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from novaxis_core.channels import InboundRequest, NormalisedInbound, ParseError, get_adapter
from novaxis_core.channels.webchat import mint_visitor_token, verify_visitor_token
from novaxis_core.inbound import IngestResult, ingest
from novaxis_core.models import Contact, Conversation, Message, Tenant
from novaxis_core.routing import resolve_tenant
from novaxis_db.session import service_session, tenant_session

log = logging.getLogger("novaxis.inbound")
router = APIRouter(prefix="/inbound", tags=["inbound"])


async def _to_inbound_request(request: Request) -> InboundRequest:
    form: dict[str, str] = {}
    body_json: dict[str, Any] | None = None
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


@router.post("/webchat/{tenant_slug}")
async def webchat(tenant_slug: str, request: Request) -> dict[str, Any]:
    req = await _to_inbound_request(request)
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
    tenant_slug: str, visitor_token: str, after: str | None = None
) -> dict[str, Any]:
    """The widget polls this for replies. Only the visitor's own conversation is readable,
    because the visitor id comes from a token we signed."""
    visitor_id = verify_visitor_token(visitor_token)
    if visitor_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad visitor token")
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
