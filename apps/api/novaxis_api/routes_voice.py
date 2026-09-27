"""Phone calls (Twilio Voice). docs/voice.md.

    call starts        POST /inbound/twilio/voice          greet (AI disclosure), listen
    caller has spoken  POST /inbound/twilio/voice/turn     run the worker turn, speak the reply
    reply not ready    POST /inbound/twilio/voice/wait     "one moment", check again

The worker turn is the same as for every other channel: same packs, same approval step,
same emergency pre-check. It runs inside the webhook so the reply can be spoken at once.
Twilio waits about 15 seconds for an answer [VERIFY], so after TURN_BUDGET seconds the
caller hears "one moment" and we check again; after MAX_WAITS the message goes to a person.

An emergency connects the caller to the on-call number if one is set. Other hand-offs end
the call honestly: the team has the message.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from novaxis_api.inline_worker import drain_for
from novaxis_api.routes_inbound import _to_inbound_request
from novaxis_core.alerts import needs_a_person
from novaxis_core.channels import InboundRequest, ParseError, get_adapter
from novaxis_core.channels.twilio_voice import connect, goodbye, hold, listen
from novaxis_core.inbound import ingest
from novaxis_core.models import ActionProposal, Contact, Conversation, Message, Tenant
from novaxis_core.routing import resolve_tenant
from novaxis_core.turn import disclosure_for
from novaxis_db.session import service_session, tenant_session

router = APIRouter(prefix="/inbound/twilio/voice", tags=["voice"])
BASE = "/inbound/twilio/voice"
TURN_BUDGET = 8.0
MAX_WAITS = 4
NOT_TAKING_CALLS = "Sorry, this number is not taking calls at the moment. Goodbye."
TOO_SLOW = (
    "Sorry, this is taking longer than it should. I have passed your message to the team. Goodbye."
)


def _xml(twiml: str) -> Response:
    return Response(content=twiml, media_type="text/xml")


async def _verified(request: Request) -> InboundRequest:
    req = await _to_inbound_request(request)
    if not get_adapter("twilio_voice").verify_signature(req):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad signature")
    return req


def _tenant_for(req: InboundRequest) -> Tenant | None:
    with service_session() as s:
        t = resolve_tenant(s, "twilio_voice", req.form.get("To", ""))
        if t is None:
            return None
        if not ((t.settings.get("channels") or {}).get("twilio_voice") or {}).get("enabled"):
            return None
        s.expunge(t)
        return t


def _voice(t: Tenant) -> str | None:
    cfg = ((t.settings.get("channels") or {}).get("twilio_voice") or {}).get("config") or {}
    return str(cfg["voice"]) if cfg.get("voice") else None


@router.post("")
async def call_started(request: Request) -> Response:
    req = await _verified(request)
    t = _tenant_for(req)
    if t is None:
        return _xml(goodbye(NOT_TAKING_CALLS))
    greeting = disclosure_for(t) or f"Hello, you are through to {t.name}. How can I help?"
    return _xml(listen(greeting, f"{BASE}/turn?t=1", _voice(t)))


def _reply_after(t: Tenant, conv_id: uuid.UUID, msg_id: uuid.UUID) -> str | None:
    """What the business has said since the caller's message, if anything yet."""
    with tenant_session(t.id) as s:
        inbound = s.get(Message, msg_id)
        if inbound is None:
            return None
        rows = s.scalars(
            select(Message)
            .where(
                Message.conversation_id == conv_id,
                Message.direction == "outbound",
                Message.created_at >= inbound.created_at,
            )
            .order_by(Message.created_at)
        )
        text = " ".join(m.body for m in rows).strip()
    if not text:
        return None
    # The greeting already said who is speaking; do not read the disclosure out twice.
    disclosure = disclosure_for(t)
    if disclosure and text.startswith(disclosure):
        text = text[len(disclosure) :].strip()
    return text.replace("\n", " ")


def _answer(t: Tenant, conv_id: uuid.UUID, msg_id: uuid.UUID, reply: str, turn: int) -> Response:
    """Speak the reply, then listen, put the caller through, or end the call."""
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        inbound = s.get(Message, msg_id)
        assert conv is not None and inbound is not None
        emergency = s.scalar(
            select(ActionProposal.id).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "escalate_emergency",
                ActionProposal.created_at >= inbound.created_at,
            )
        )
        handed_over = conv.status in ("waiting_human", "closed")
    voice = _voice(t)
    if emergency:
        phones = [
            c.get("phone") for c in t.settings.get("escalation_contacts") or [] if c.get("phone")
        ]
        if phones:
            return _xml(
                connect(
                    f"{reply} I am putting you through to the on-call team now.", phones[0], voice
                )
            )
        return _xml(goodbye(reply, voice))
    if handed_over:
        return _xml(goodbye(f"{reply} I have passed this to the team. Goodbye.", voice))
    return _xml(listen(reply, f"{BASE}/turn?t={turn + 1}", voice))


@router.post("/turn")
async def caller_spoke(request: Request) -> Response:
    req = await _verified(request)
    t = _tenant_for(req)
    if t is None:
        return _xml(goodbye(NOT_TAKING_CALLS))
    turn = int(req.query.get("t", "1") or 1)
    try:
        inbound = get_adapter("twilio_voice").parse_inbound(req)
    except ParseError:
        return _xml(
            listen(
                "Sorry, I did not catch that. Could you say it again?",
                f"{BASE}/turn?t={turn}",
                _voice(t),
            )
        )
    with tenant_session(t.id) as s:
        result = ingest(s, t, inbound)
    if result.job_id is None and not result.duplicate:
        return _xml(
            goodbye("Thank you. A member of the team has your message. Goodbye.", _voice(t))
        )
    drain_for(TURN_BUDGET)
    reply = _reply_after(t, result.conversation_id, result.message_id)
    if reply is None:
        return _xml(hold(_wait_url(result.conversation_id, result.message_id, turn, 1), _voice(t)))
    return _answer(t, result.conversation_id, result.message_id, reply, turn)


def _wait_url(conv_id: uuid.UUID, msg_id: uuid.UUID, turn: int, n: int) -> str:
    return f"{BASE}/wait?c={conv_id}&m={msg_id}&t={turn}&n={n}"


@router.post("/wait")
async def waiting(request: Request) -> Response:
    req = await _verified(request)
    t = _tenant_for(req)
    if t is None:
        return _xml(goodbye(NOT_TAKING_CALLS))
    try:
        conv_id, msg_id = uuid.UUID(req.query["c"]), uuid.UUID(req.query["m"])
        turn, n = int(req.query.get("t", "1")), int(req.query.get("n", "1"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad wait link") from exc
    if not _caller_owns(t, conv_id, req.form.get("From", "")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such call")
    drain_for(TURN_BUDGET)
    reply = _reply_after(t, conv_id, msg_id)
    if reply is not None:
        return _answer(t, conv_id, msg_id, reply, turn)
    if n >= MAX_WAITS:
        with tenant_session(t.id) as s:
            conv = s.get(Conversation, conv_id)
            if conv is not None and conv.status not in ("waiting_human", "closed"):
                conv.status = "waiting_human"
                needs_a_person(s, t.id, conv_id)
        return _xml(
            goodbye(
                TOO_SLOW,
                _voice(t),
            )
        )
    return _xml(hold(_wait_url(conv_id, msg_id, turn, n + 1), _voice(t)))


def _caller_owns(t: Tenant, conv_id: uuid.UUID, caller: str) -> bool:
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        contact = s.get(Contact, conv.contact_id) if conv else None
        return bool(
            conv and contact and conv.channel == "twilio_voice" and caller in contact.phones
        )
