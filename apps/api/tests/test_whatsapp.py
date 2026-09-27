"""WhatsApp (Meta Cloud API): handshake, signed webhooks, several messages per call,
receipts ignored, replays harmless, sending, photos, voice notes, the 24-hour window, and
one customer across SMS and WhatsApp."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from novaxis_api.main import create_app
from novaxis_core.channels import register_adapter
from novaxis_core.channels.whatsapp import MEDIA_PREFIX, VOICE_NOTE, WhatsAppAdapter, signature
from novaxis_core.executors import execute
from novaxis_core.media import fetch_media
from novaxis_core.models import ActionProposal, Contact, Conversation, Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

SECRET = "meta-app-secret"
HVAC_WA = "100000000000001"


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for k, v in {
        "NOVAXIS_WHATSAPP_APP_SECRET": SECRET,
        "NOVAXIS_WHATSAPP_VERIFY_TOKEN": "verify-me",
        "NOVAXIS_WHATSAPP_ACCESS_TOKEN": "wa-token",
        "NOVAXIS_WHATSAPP_API_BASE": "https://graph.test/v99",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
    yield TestClient(create_app())
    register_adapter(WhatsAppAdapter())
    get_settings.cache_clear()


def _payload(
    *messages: dict[str, Any], to: str = HVAC_WA, statuses: bool = False
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": to, "display_phone_number": "447700900001"},
        "contacts": [{"wa_id": m["from"], "profile": {"name": "Wendy WhatsApp"}} for m in messages],
        "messages": list(messages),
    }
    if statuses:
        value = {"metadata": value["metadata"], "statuses": [{"id": "wamid.x", "status": "read"}]}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}],
    }


def _post(c: TestClient, body: dict[str, Any], secret: str = SECRET):  # type: ignore[no-untyped-def]
    raw = json.dumps(body).encode()
    return c.post(
        "/inbound/whatsapp",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(secret, raw)},
    )


def _text(sender: str, text: str, mid: str | None = None) -> dict[str, Any]:
    return {
        "from": sender,
        "id": mid or f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": text},
    }


def _wa() -> str:
    return f"4477009{uuid.uuid4().int % 100000:05d}"


def test_meta_handshake_needs_the_verify_token(client: TestClient) -> None:
    ok = client.get(
        "/inbound/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"},
    )
    assert ok.status_code == 200 and ok.text == "12345"
    bad = client.get(
        "/inbound/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"},
    )
    assert bad.status_code == 403


def test_signed_messages_are_ingested_once_and_receipts_or_strangers_are_ignored(
    client: TestClient,
) -> None:
    sender = _wa()
    first, second = _text(sender, "Hi, is Saturday free?"), _text(sender, "For a boiler service")
    r = _post(client, _payload(first, second))
    assert r.status_code == 200 and r.json() == {"ok": True, "messages": 2, "ingested": 2}
    assert _post(client, _payload(first)).json()["ingested"] == 1, "a replay is accepted..."
    with service_session() as s:
        tid = s.scalar(select(Tenant.id).where(Tenant.slug == "demo-hvac"))
    with tenant_session(tid) as s:  # type: ignore[arg-type]
        contact = s.scalar(select(Contact).where(Contact.phones.contains([f"+{sender}"])))
        assert contact is not None and contact.display_name == "Wendy WhatsApp"
        conv = s.scalar(select(Conversation).where(Conversation.contact_id == contact.id))
        assert conv is not None and conv.channel == "whatsapp"
        bodies = [
            m.body
            for m in s.scalars(
                select(Message).where(
                    Message.conversation_id == conv.id, Message.direction == "inbound"
                )
            )
        ]
    assert bodies.count("Hi, is Saturday free?") == 1, "...but not stored twice"
    assert _post(client, _payload(statuses=True)).json()["ingested"] == 0
    assert _post(client, _payload(_text(_wa(), "hello"), to="999")).json()["ingested"] == 0
    assert _post(client, _payload(_text(_wa(), "hello")), secret="wrong").status_code == 403


def test_voice_notes_ask_for_text_and_photos_are_fetched_with_the_token(client: TestClient) -> None:
    sender = _wa()
    photo = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "image",
        "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "the leak"},
    }
    note = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "audio",
        "audio": {"id": "A1", "mime_type": "audio/ogg", "voice": True},
    }
    assert _post(client, _payload(photo, note)).json()["ingested"] == 2
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    with tenant_session(t.id) as s:
        rows = {
            m.body: m
            for m in s.scalars(
                select(Message).where(Message.provider_ref.in_([photo["id"], note["id"]]))
            )
        }
        assert VOICE_NOTE in rows
        pic = rows["the leak"]
        assert pic.media[0]["url"] == MEDIA_PREFIX + "MEDIA1"
        pic_id = pic.id
    seen: list[str] = []

    def graph(req: httpx.Request) -> httpx.Response:
        seen.append(f"{req.url} {req.headers.get('authorization')}")
        if str(req.url).endswith("/MEDIA1"):
            return httpx.Response(
                200, json={"url": "https://lookaside.test/file", "mime_type": "image/jpeg"}
            )
        return httpx.Response(200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})

    with tenant_session(t.id) as s:
        assert fetch_media(s, t, pic_id, transport=httpx.MockTransport(graph)) == 1
    assert seen == [
        "https://graph.test/v99/MEDIA1 Bearer wa-token",
        "https://lookaside.test/file Bearer wa-token",
    ]


def _reply(tenant: Tenant, conv_id: uuid.UUID, text: str) -> Any:
    with tenant_session(tenant.id) as s:
        p = ActionProposal(
            tenant_id=tenant.id,
            conversation_id=conv_id,
            kind="reply",
            params={"text": text},
            risk="low",
            state="approved",
        )
        s.add(p)
        s.flush()
        return execute(s, tenant, p)


def test_replies_go_out_within_24_hours_and_later_ones_go_to_a_person(client: TestClient) -> None:
    sent: list[dict[str, Any]] = []

    def meta(req: httpx.Request) -> httpx.Response:
        sent.append(
            {"url": str(req.url), "auth": req.headers["authorization"], **json.loads(req.content)}
        )
        return httpx.Response(200, json={"messages": [{"id": "wamid.out1"}]})

    register_adapter(WhatsAppAdapter(transport=httpx.MockTransport(meta)))
    sender = _wa()
    _post(client, _payload(_text(sender, "Can you come Monday?")))
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        conv_id = s.scalar(
            select(Conversation.id)
            .join(Contact, Contact.id == Conversation.contact_id)
            .where(Contact.phones.contains([f"+{sender}"]))
        )
    assert _reply(t, conv_id, "Yes, Monday morning works.").ok
    assert (
        sent[0]["url"] == f"https://graph.test/v99/{HVAC_WA}/messages"
        and sent[0]["auth"] == "Bearer wa-token"
    )
    assert sent[0]["to"] == sender and sent[0]["text"]["body"] == "Yes, Monday morning works."

    with service_session() as s:  # the customer's last message was 25 hours ago
        s.execute(
            update(Message)
            .where(Message.conversation_id == conv_id)
            .values(created_at=datetime.now(UTC) - timedelta(hours=25))
        )
    res = _reply(t, conv_id, "Just checking in")
    assert not res.ok and "24-hour" in (res.error or "")
    assert len(sent) == 1, "nothing was sent to Meta"
    with service_session() as s:
        assert s.get(Conversation, conv_id).status == "waiting_human"  # type: ignore[union-attr]
        assert s.scalar(
            select(Job).where(
                Job.kind == "alert_staff", Job.payload["url"].astext == f"/conversations/{conv_id}"
            )
        )


def test_one_customer_across_sms_and_whatsapp(client: TestClient) -> None:
    sender = _wa()
    _post(client, _payload(_text(sender, "whatsapp hello")))
    from novaxis_core.channels import NormalisedInbound
    from novaxis_core.inbound import ingest

    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="twilio_sms",
                provider_ref=f"SM{uuid.uuid4().hex}",
                tenant_ref="+15005550006",
                sender_phone=f"+{sender}",
                body="sms hello",
            ),
        )
        wa_contact = s.scalar(select(Contact).where(Contact.phones.contains([f"+{sender}"])))
        assert wa_contact is not None and r.contact_id == wa_contact.id
