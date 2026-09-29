"""WhatsApp through Twilio: signed like SMS, numbers written whatsapp:+44..., routed by
the business's WhatsApp number or else its Twilio SMS number, replies sent back through
Twilio as WhatsApp, the 24-hour rule kept, and one customer across SMS and WhatsApp.
Also: Twilio signatures are accepted for whichever of our addresses Twilio called."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from novaxis_api.main import create_app
from novaxis_core.channels import register_adapter
from novaxis_core.channels.twilio_sms import compute_signature
from novaxis_core.channels.twilio_whatsapp import TwilioWhatsAppAdapter
from novaxis_core.models import Contact, Conversation, Job, Message, Tenant
from novaxis_core.outbound import ReplyWindowClosedError, send_message
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

TOKEN = "twilio-test-token"
HVAC_SMS = "+15005550006"
SANDBOX = "+14155550199"  # not the seeded demo sandbox number: one business per number


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for k, v in {
        "NOVAXIS_TWILIO_AUTH_TOKEN": TOKEN,
        "NOVAXIS_TWILIO_ACCOUNT_SID": "ACtest",
        "NOVAXIS_PUBLIC_BASE_URL": "https://novaxis-api-long-name.vercel.app",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
        for slug, cfg in (("demo-hvac", {}), ("demo-dental", {"number": SANDBOX})):
            t = s.scalar(select(Tenant).where(Tenant.slug == slug))
            assert t is not None
            settings = json.loads(json.dumps(t.settings))
            settings["channels"]["twilio_whatsapp"] = {"enabled": True, "config": cfg}
            t.settings = settings
    # Replies the assistant queues must never reach the real Twilio, here or in any later
    # test's queue drain.
    register_adapter(TwilioWhatsAppAdapter(transport=httpx.MockTransport(_ok)))
    yield TestClient(create_app())
    with service_session() as s:
        s.execute(update(Job).where(Job.state == "queued").values(state="done"))
    register_adapter(TwilioWhatsAppAdapter())
    get_settings.cache_clear()


def _ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(201, json={"sid": "SMok"})


def _post(c: TestClient, form: dict[str, str], host: str = "novaxis-api.vercel.app"):  # type: ignore[no-untyped-def]
    """Signed for the address Twilio was told to call (the short one), not the configured
    long one: both must work."""
    url = f"https://{host}/inbound/twilio/whatsapp"
    sig = compute_signature(TOKEN, url, form)
    return c.post(
        "/inbound/twilio/whatsapp",
        data=form,
        headers={"X-Twilio-Signature": sig, "X-Forwarded-Host": host},
    )


def _msg(to: str, sender: str, body: str) -> dict[str, str]:
    return {
        "MessageSid": f"SM{uuid.uuid4().hex}",
        "From": f"whatsapp:{sender}",
        "To": f"whatsapp:{to}",
        "Body": body,
        "NumMedia": "0",
        "ProfileName": "Tia Twilio",
    }


def _phone() -> str:
    return f"+4477009{uuid.uuid4().int % 100000:05d}"


def _conversation(phone: str) -> tuple[Tenant, uuid.UUID]:
    with service_session() as s:
        row = s.execute(
            select(Tenant, Conversation.id)
            .join(Conversation, Conversation.tenant_id == Tenant.id)
            .join(Contact, Contact.id == Conversation.contact_id)
            .where(Contact.phones.contains([phone]), Conversation.channel == "twilio_whatsapp")
        ).first()
        assert row is not None
        s.expunge(row[0])
        return row[0], row[1]


def test_messages_route_by_whatsapp_number_or_the_sms_number(client: TestClient) -> None:
    a, b = _phone(), _phone()
    assert _post(client, _msg(HVAC_SMS, a, "Boiler banging")).status_code == 200
    assert _post(client, _msg(SANDBOX, b, "Tooth hurts")).status_code == 200
    assert _conversation(a)[0].slug == "demo-hvac", "no WhatsApp number: the SMS number"
    assert _conversation(b)[0].slug == "demo-dental", "its own WhatsApp number"
    t, conv_id = _conversation(a)
    with tenant_session(t.id) as s:
        contact = s.scalar(select(Contact).where(Contact.phones.contains([a])))
        assert contact is not None and contact.display_name == "Tia Twilio"
    assert _post(client, _msg("+19999999999", _phone(), "hi")).status_code == 404


def test_signatures_are_checked_for_every_address_we_answer_on(client: TestClient) -> None:
    form = _msg(HVAC_SMS, _phone(), "hello")
    assert _post(client, form, host="novaxis-api-long-name.vercel.app").status_code == 200
    forged = client.post(
        "/inbound/twilio/whatsapp", data=form, headers={"X-Twilio-Signature": "bad"}
    )
    assert forged.status_code == 403
    other = compute_signature(
        "someone-elses-token", "https://novaxis-api.vercel.app/inbound/twilio/whatsapp", form
    )
    assert (
        client.post(
            "/inbound/twilio/whatsapp",
            data=form,
            headers={"X-Twilio-Signature": other, "X-Forwarded-Host": "novaxis-api.vercel.app"},
        ).status_code
        == 403
    )


def test_replies_go_back_as_whatsapp_and_the_24_hour_rule_holds(client: TestClient) -> None:
    sent: list[dict[str, Any]] = []

    def twilio(req: httpx.Request) -> httpx.Response:
        sent.append({k: v[0] for k, v in parse_qs(req.content.decode()).items()})
        return httpx.Response(201, json={"sid": f"SM{len(sent)}"})

    register_adapter(TwilioWhatsAppAdapter(transport=httpx.MockTransport(twilio)))
    phone = _phone()
    _post(client, _msg(HVAC_SMS, phone, "Can you come Monday?"))
    t, conv_id = _conversation(phone)
    with tenant_session(t.id) as s:
        m = Message(
            tenant_id=t.id,
            conversation_id=conv_id,
            direction="outbound",
            channel="twilio_whatsapp",
            author="worker",
            body="Yes, Monday works.",
        )
        s.add(m)
        s.flush()
        send_message(s, t, m.id)
    assert sent[0] == {
        "From": f"whatsapp:{HVAC_SMS}",
        "To": f"whatsapp:{phone}",
        "Body": "Yes, Monday works.",
    }

    with service_session() as s:
        s.execute(
            update(Message)
            .where(Message.conversation_id == conv_id)
            .values(created_at=datetime.now(UTC) - timedelta(hours=25))
        )
    with tenant_session(t.id) as s:
        late = Message(
            tenant_id=t.id,
            conversation_id=conv_id,
            direction="outbound",
            channel="twilio_whatsapp",
            author="worker",
            body="Just checking in",
        )
        s.add(late)
        s.flush()
        with pytest.raises(ReplyWindowClosedError):
            send_message(s, t, late.id)
    assert len(sent) == 1


def test_one_customer_across_sms_and_whatsapp(client: TestClient) -> None:
    phone = _phone()
    _post(client, _msg(HVAC_SMS, phone, "whatsapp hello"))
    form = {
        "MessageSid": f"SM{uuid.uuid4().hex}",
        "From": phone,
        "To": HVAC_SMS,
        "Body": "sms hello",
    }
    sig = compute_signature(TOKEN, "https://novaxis-api.vercel.app/inbound/twilio/sms", form)
    r = client.post(
        "/inbound/twilio/sms",
        data=form,
        headers={"X-Twilio-Signature": sig, "X-Forwarded-Host": "novaxis-api.vercel.app"},
    )
    assert r.status_code == 200
    with service_session() as s:
        contacts = list(s.scalars(select(Contact).where(Contact.phones.contains([phone]))))
        assert len(contacts) == 1
