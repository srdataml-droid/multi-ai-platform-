"""Each adapter turns its provider's fixture into a NormalisedInbound, and refuses forgeries."""

from __future__ import annotations

import json

import httpx
import pytest

from novaxis_core.channels import InboundRequest, ParseError
from novaxis_core.channels.email_postmark import PostmarkEmailAdapter
from novaxis_core.channels.twilio_sms import TwilioSmsAdapter, compute_signature
from novaxis_core.channels.webchat import WebchatAdapter, mint_visitor_token, verify_visitor_token
from novaxis_core.settings import get_settings

TWILIO_FORM = {
    "MessageSid": "SM123",
    "From": "+447700900123",
    "To": "+15005550006",
    "Body": "My boiler is broken",
    "NumMedia": "1",
    "MediaUrl0": "https://api.twilio.com/media/1",
    "MediaContentType0": "image/jpeg",
    "FromCity": "London",
}

POSTMARK_JSON = {
    "MessageID": "pm-abc",
    "From": "Alice Smith <Alice@Example.com>",
    "FromFull": {"Email": "Alice@Example.com", "Name": "Alice Smith"},
    "To": "demo-hvac@inbound.novaxis.test",
    "ToFull": [{"Email": "demo-hvac@inbound.novaxis.test", "Name": ""}],
    "Subject": "Boiler",
    "TextBody": "Hello,\n\nMy boiler is broken.\n\nOn Mon, you wrote: ...",
    "StrippedTextReply": "My boiler is broken.",
    "Attachments": [{"Name": "photo.jpg", "ContentType": "image/jpeg"}],
}


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_TWILIO_AUTH_TOKEN", "twilio-test-token")
    monkeypatch.setenv("NOVAXIS_POSTMARK_INBOUND_TOKEN", "pm-inbound-token")
    monkeypatch.setenv("NOVAXIS_PUBLIC_BASE_URL", "https://api.example.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_twilio_parses_body_media_and_routes_by_to_number() -> None:
    req = InboundRequest(
        url="https://api.example.test/inbound/twilio/sms", headers={}, form=TWILIO_FORM
    )
    inbound = TwilioSmsAdapter().parse_inbound(req)
    assert inbound.channel == "twilio_sms"
    assert inbound.provider_ref == "SM123"
    assert inbound.tenant_ref == "+15005550006"
    assert inbound.sender_phone == "+447700900123"
    assert inbound.body == "My boiler is broken"
    assert inbound.media[0].content_type == "image/jpeg"
    assert inbound.raw == {"FromCity": "London"}


def test_twilio_signature_accepts_genuine_and_rejects_forged() -> None:
    url = "https://api.example.test/inbound/twilio/sms"
    good = compute_signature("twilio-test-token", url, TWILIO_FORM)
    adapter = TwilioSmsAdapter()
    # The app sees an internal URL; verification rebuilds the public one.
    internal = "http://10.0.0.5:8000/inbound/twilio/sms"
    assert adapter.verify_signature(
        InboundRequest(url=internal, headers={"X-Twilio-Signature": good}, form=TWILIO_FORM)
    )
    assert not adapter.verify_signature(
        InboundRequest(url=internal, headers={"X-Twilio-Signature": "forged"}, form=TWILIO_FORM)
    )
    tampered = {**TWILIO_FORM, "Body": "different"}
    assert not adapter.verify_signature(
        InboundRequest(url=internal, headers={"X-Twilio-Signature": good}, form=tampered)
    )


def test_twilio_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_TWILIO_AUTH_TOKEN", "")
    get_settings.cache_clear()
    req = InboundRequest(url="x", headers={"X-Twilio-Signature": "anything"}, form=TWILIO_FORM)
    assert not TwilioSmsAdapter().verify_signature(req)


def test_twilio_send_posts_to_messages_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["data"] = request.content.decode()
        return httpx.Response(201, json={"sid": "SM999"})

    adapter = TwilioSmsAdapter(transport=httpx.MockTransport(handler))
    ref = adapter.send(
        to="+447700900123", body="Hi", tenant_channel_config={"number": "+15005550006"}
    )
    assert ref.provider_ref == "SM999"
    assert "Messages.json" in str(seen["url"])
    assert "From=%2B15005550006" in str(seen["data"])


def test_postmark_parses_stripped_reply_and_lowercases_sender() -> None:
    req = InboundRequest(
        url="x", headers={}, json=POSTMARK_JSON, query={"token": "pm-inbound-token"}
    )
    adapter = PostmarkEmailAdapter()
    assert adapter.verify_signature(req)
    inbound = adapter.parse_inbound(req)
    assert inbound.sender_email == "alice@example.com"
    assert inbound.sender_name == "Alice Smith"
    assert inbound.tenant_ref == "demo-hvac@inbound.novaxis.test"
    assert inbound.body == "Subject: Boiler\n\nMy boiler is broken."
    assert inbound.media[0].url == "postmark-attachment:photo.jpg"


def test_postmark_rejects_wrong_or_missing_token() -> None:
    adapter = PostmarkEmailAdapter()
    assert not adapter.verify_signature(InboundRequest(url="x", headers={}, json=POSTMARK_JSON))
    assert not adapter.verify_signature(
        InboundRequest(url="x", headers={}, json=POSTMARK_JSON, query={"token": "nope"})
    )
    assert adapter.verify_signature(
        InboundRequest(url="x", headers={"X-Novaxis-Inbound-Token": "pm-inbound-token"}, json={})
    )


def test_postmark_send_uses_server_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Postmark-Server-Token"] == ""
        payload = json.loads(request.content)
        assert payload["To"] == "alice@example.com" and payload["From"] == "hello@demo.test"
        return httpx.Response(200, json={"MessageID": "pm-out-1"})

    adapter = PostmarkEmailAdapter(transport=httpx.MockTransport(handler))
    ref = adapter.send(
        to="alice@example.com", body="Hi", tenant_channel_config={"from_address": "hello@demo.test"}
    )
    assert ref.provider_ref == "pm-out-1"


def test_webchat_mints_token_for_new_visitor_and_keeps_it_for_returning() -> None:
    adapter = WebchatAdapter()
    first = adapter.parse_inbound(
        InboundRequest(url="x", headers={}, json={"body": "hi"}, query={"tenant": "demo-hvac"})
    )
    assert first.sender_visitor_id
    token = mint_visitor_token(first.sender_visitor_id)
    second = adapter.parse_inbound(
        InboundRequest(
            url="x",
            headers={},
            json={"body": "again", "visitor_token": token},
            query={"tenant": "demo-hvac"},
        )
    )
    assert second.sender_visitor_id == first.sender_visitor_id
    forged = adapter.parse_inbound(
        InboundRequest(
            url="x",
            headers={},
            json={"body": "x", "visitor_token": first.sender_visitor_id + ".deadbeef"},
            query={"tenant": "demo-hvac"},
        )
    )
    assert forged.sender_visitor_id != first.sender_visitor_id


def test_visitor_token_roundtrip_and_tamper() -> None:
    tok = mint_visitor_token("abc")
    assert verify_visitor_token(tok) == "abc"
    assert verify_visitor_token(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None
    assert verify_visitor_token(None) is None


def test_webchat_rejects_empty_body() -> None:
    with pytest.raises(ParseError):
        WebchatAdapter().parse_inbound(
            InboundRequest(url="x", headers={}, json={"body": "  "}, query={"tenant": "t"})
        )
