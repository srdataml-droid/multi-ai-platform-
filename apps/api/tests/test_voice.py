"""Phone calls: greet with the AI disclosure, run the same worker turn for each thing the
caller says, speak the reply, put emergencies through to the on-call number, and never
leave a caller hanging when the reply is slow."""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api import inline_worker
from novaxis_api.main import create_app
from novaxis_core.channels.twilio_sms import compute_signature
from novaxis_core.models import Contact, Conversation, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

HVAC_NUMBER = "+15005550006"


@pytest.fixture
def env(migrated: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    with service_session(migrated) as s:
        seed(s)

    def make(**extra: str) -> TestClient:
        for k, v in {
            "NOVAXIS_TWILIO_AUTH_TOKEN": "twilio-test-token",
            "NOVAXIS_PUBLIC_BASE_URL": "http://testserver",
            "NOVAXIS_LLM_PROVIDER": "fake",
            **extra,
        }.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        inline_worker._handlers.cache_clear()
        return TestClient(create_app())

    yield make
    get_settings.cache_clear()
    inline_worker._handlers.cache_clear()


def _call(
    c: TestClient,
    path: str,
    caller: str,
    speech: str | None = None,
    to: str = HVAC_NUMBER,
    sid: str = "CA1",
):  # type: ignore[no-untyped-def]
    form = {"CallSid": sid, "From": caller, "To": to}
    if speech is not None:
        form["SpeechResult"] = speech
    sig = compute_signature("twilio-test-token", f"http://testserver{path}", form)
    return c.post(path, data=form, headers={"X-Twilio-Signature": sig})


def _caller() -> str:
    return f"+4477009{uuid.uuid4().int % 100000:05d}"


def test_a_call_is_greeted_with_the_ai_disclosure_and_listens(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    r = _call(c, "/inbound/twilio/voice", _caller())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    assert "AI assistant" in r.text and "Gather" in r.text
    assert 'action="/inbound/twilio/voice/turn?t=1"' in r.text
    forged = c.post("/inbound/twilio/voice", data={"CallSid": "x", "From": "+1", "To": HVAC_NUMBER})
    assert forged.status_code == 403
    assert (
        "not taking calls" in _call(c, "/inbound/twilio/voice", _caller(), to="+19999999999").text
    )


def test_what_the_caller_says_gets_a_spoken_reply_and_the_call_goes_on(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    caller, sid = _caller(), f"CA{uuid.uuid4().hex[:8]}"
    r = _call(
        c, "/inbound/twilio/voice/turn?t=1", caller, "My boiler is making a banging noise", sid=sid
    )
    assert r.status_code == 200
    said = re.findall(r"<Say[^>]*>(.*?)</Say>", r.text)
    assert said and "How can we help" in said[0], r.text
    assert "AI assistant" not in said[0], "the disclosure was already spoken in the greeting"
    assert 'action="/inbound/twilio/voice/turn?t=2"' in r.text
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        tid = t.id
    with tenant_session(tid) as s:
        contact = s.scalar(select(Contact).where(Contact.phones.contains([caller])))
        assert contact is not None, "callers are matched by phone number, like texts"
        conv = s.scalar(select(Conversation).where(Conversation.contact_id == contact.id))
        assert conv is not None and conv.channel == "twilio_voice"
        conv_id = conv.id
        bodies = [
            m.body for m in s.scalars(select(Message).where(Message.conversation_id == conv_id))
        ]
        assert "My boiler is making a banging noise" in bodies
    # Twilio sending the same turn twice does not run it twice.
    again = _call(
        c, "/inbound/twilio/voice/turn?t=1", caller, "My boiler is making a banging noise", sid=sid
    )
    assert again.status_code == 200
    with tenant_session(tid) as s:
        n = len(
            list(
                s.scalars(
                    select(Message).where(
                        Message.conversation_id == conv_id, Message.direction == "inbound"
                    )
                )
            )
        )
        assert n == 1


def test_an_emergency_call_is_put_through_to_the_on_call_number(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    r = _call(
        c,
        "/inbound/twilio/voice/turn?t=1",
        _caller(),
        "I can smell gas in the kitchen",
        sid=f"CA{uuid.uuid4().hex[:8]}",
    )
    assert "<Dial>+447700900000</Dial>" in r.text, r.text
    assert "putting you through" in r.text


def test_silence_is_asked_again_and_a_slow_reply_ends_with_a_person_not_a_dead_line(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    caller = _call(c, "/inbound/twilio/voice/turn?t=3", _caller(), speech="")
    assert "did not catch that" in caller.text and "turn?t=3" in caller.text

    c = env(NOVAXIS_WORKER_ENABLED="false")  # no reply will come
    who = _caller()
    r = _call(
        c,
        "/inbound/twilio/voice/turn?t=1",
        who,
        "Can someone come tomorrow?",
        sid=f"CA{uuid.uuid4().hex[:8]}",
    )
    assert "One moment" in r.text and "<Redirect" in r.text
    link = re.search(r"<Redirect[^>]*>(.*?)</Redirect>", r.text).group(1).replace("&amp;", "&")  # type: ignore[union-attr]
    for n in range(1, 5):
        assert f"n={n}" in link
        r = _call(c, link, who)
        if n < 4:
            link = (
                re.search(r"<Redirect[^>]*>(.*?)</Redirect>", r.text).group(1).replace("&amp;", "&")
            )  # type: ignore[union-attr]
    assert "passed your message to the team" in r.text and "<Hangup/>" in r.text
    conv_id = uuid.UUID(re.search(r"c=([0-9a-f-]+)", link).group(1))  # type: ignore[union-attr]
    with service_session() as s:
        assert s.get(Conversation, conv_id).status == "waiting_human"  # type: ignore[union-attr]
    # Someone else's call cannot read this conversation through the wait link.
    assert _call(c, link, _caller()).status_code == 404
