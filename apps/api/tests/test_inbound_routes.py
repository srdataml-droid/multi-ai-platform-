from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from novaxis_api.main import create_app
from novaxis_core.channels.twilio_sms import compute_signature
from novaxis_core.models import Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NOVAXIS_TWILIO_AUTH_TOKEN", "twilio-test-token")
    monkeypatch.setenv("NOVAXIS_POSTMARK_INBOUND_TOKEN", "pm-inbound-token")
    monkeypatch.setenv("NOVAXIS_PUBLIC_BASE_URL", "http://testserver")
    get_settings.cache_clear()
    with service_session(migrated) as s:
        seed(s)
    yield TestClient(create_app())
    get_settings.cache_clear()


def _hvac_id() -> uuid.UUID:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        return t.id


def _job_count(tenant_id: uuid.UUID) -> int:
    with tenant_session(tenant_id) as s:
        return s.scalar(select(func.count()).select_from(Job)) or 0


def test_webchat_message_creates_rows_and_returns_token(client: TestClient) -> None:
    tid = _hvac_id()
    before = _job_count(tid)
    r = client.post(
        "/inbound/webchat/demo-hvac", json={"body": "Hi, boiler trouble", "name": "Vis"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["visitor_token"] and body["conversation_id"]
    assert _job_count(tid) == before + 1
    # Returning visitor with the token threads into the same conversation.
    r2 = client.post(
        "/inbound/webchat/demo-hvac",
        json={"body": "still there?", "visitor_token": body["visitor_token"]},
    )
    assert r2.json()["conversation_id"] == body["conversation_id"]
    # And can read their own messages back.
    r3 = client.get(
        "/inbound/webchat/demo-hvac/messages", params={"visitor_token": body["visitor_token"]}
    )
    assert [m["body"] for m in r3.json()["messages"]] == ["Hi, boiler trouble", "still there?"]


def test_webchat_unknown_tenant_is_404(client: TestClient) -> None:
    assert client.post("/inbound/webchat/nope", json={"body": "hi"}).status_code == 404


def test_webchat_messages_with_forged_token_is_401(client: TestClient) -> None:
    r = client.get("/inbound/webchat/demo-hvac/messages", params={"visitor_token": "abc.def"})
    assert r.status_code == 401


def test_twilio_bad_signature_is_403_and_writes_nothing(client: TestClient) -> None:
    tid = _hvac_id()
    before = _job_count(tid)
    form = {
        "MessageSid": f"SM{uuid.uuid4().hex[:10]}",
        "From": "+447700900999",
        "To": "+15005550006",
        "Body": "hi",
    }
    r = client.post("/inbound/twilio/sms", data=form, headers={"X-Twilio-Signature": "forged"})
    assert r.status_code == 403
    assert _job_count(tid) == before


def test_twilio_good_signature_ingests_and_replay_is_noop(client: TestClient) -> None:
    tid = _hvac_id()
    before = _job_count(tid)
    form = {
        "MessageSid": f"SM{uuid.uuid4().hex[:10]}",
        "From": "+447700900998",
        "To": "+15005550006",
        "Body": "hi",
    }
    sig = compute_signature("twilio-test-token", "http://testserver/inbound/twilio/sms", form)
    r = client.post("/inbound/twilio/sms", data=form, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200 and r.text == "<Response></Response>"
    assert _job_count(tid) == before + 1
    r = client.post("/inbound/twilio/sms", data=form, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200
    assert _job_count(tid) == before + 1
    with tenant_session(tid) as s:
        n = s.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.provider_ref == form["MessageSid"])
        )
        assert n == 1


def test_postmark_wrong_token_is_403(client: TestClient) -> None:
    payload = {
        "MessageID": "x",
        "From": "a@b.c",
        "FromFull": {"Email": "a@b.c"},
        "To": "demo-hvac@inbound.novaxis.test",
        "TextBody": "hi",
    }
    assert (
        client.post("/inbound/email/postmark", json=payload, params={"token": "nope"}).status_code
        == 403
    )


def test_postmark_good_token_ingests(client: TestClient) -> None:
    tid = _hvac_id()
    before = _job_count(tid)
    payload = {
        "MessageID": f"pm-{uuid.uuid4().hex[:8]}",
        "FromFull": {"Email": "Someone@Example.com", "Name": "Some One"},
        "ToFull": [{"Email": "demo-hvac@inbound.novaxis.test"}],
        "Subject": "Help",
        "StrippedTextReply": "My heating is off.",
    }
    r = client.post("/inbound/email/postmark", json=payload, params={"token": "pm-inbound-token"})
    assert r.status_code == 200 and r.json() == {"ok": True, "duplicate": False}
    assert _job_count(tid) == before + 1
