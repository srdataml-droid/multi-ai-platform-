"""Voice notes: a customer's audio is fetched and transcribed with Whisper before the
assistant answers; the emergency check hears it ("I can smell gas" said out loud); staff
and a business's own agent see the transcript; and when speech to text is not set up or
fails, the assistant asks the customer to type instead of guessing."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core import media as media_mod
from novaxis_core.channels.whatsapp import signature
from novaxis_core.llm import FakeLLM
from novaxis_core.media import UNHEARD
from novaxis_core.models import ActionProposal, Conversation, Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.stt import OpenAICompatSTT, TranscriptionError
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack
from novaxis_worker.loop import Picked, _handle_fetch_media, run_job

SECRET = "meta-app-secret"
HVAC_WA = "100000000000001"
OGG = b"OggS\x00\x02voice-note-bytes"


@pytest.fixture
def client(migrated: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for k, v in {
        "NOVAXIS_WHATSAPP_APP_SECRET": SECRET,
        "NOVAXIS_WHATSAPP_ACCESS_TOKEN": "wa-token",
        "NOVAXIS_STT_PROVIDER": "fake",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    # The WhatsApp media download (two Graph calls) is tested in test_whatsapp.py.
    monkeypatch.setattr(media_mod, "download", lambda media_id, transport=None: (OGG, "audio/ogg"))
    with service_session(migrated) as s:
        seed(s)
    yield TestClient(create_app())
    get_settings.cache_clear()


def _voice_note(
    c: TestClient, said: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Tenant, uuid.UUID]:
    """A WhatsApp voice note that Whisper will hear as `said`; the media job runs."""
    monkeypatch.setenv("NOVAXIS_FAKE_TRANSCRIPT", said)
    get_settings.cache_clear()
    sender = f"4477009{uuid.uuid4().int % 100000:05d}"
    note = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "audio",
        "audio": {
            "id": f"A{uuid.uuid4().hex[:6]}",
            "mime_type": "audio/ogg; codecs=opus",
            "voice": True,
        },
    }
    body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": HVAC_WA},
                            "contacts": [{"wa_id": sender, "profile": {"name": "Val Voice"}}],
                            "messages": [note],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(body).encode()
    r = c.post(
        "/inbound/whatsapp",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(SECRET, raw)},
    )
    assert r.json()["ingested"] == 1
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        msg = s.scalar(select(Message).where(Message.provider_ref == note["id"]))
        assert msg is not None
        conv_id = msg.conversation_id
        fetch = s.scalar(
            select(Job).where(
                Job.kind == "fetch_media", Job.payload["message_id"].astext == str(msg.id)
            )
        )
        assert fetch is not None and fetch.payload["then_turn"] is True
        assert fetch.payload["conversation_id"] == str(conv_id), "a failure hands over"
        assert (
            s.scalar(
                select(Job).where(
                    Job.kind == "worker_turn", Job.payload["conversation_id"].astext == str(conv_id)
                )
            )
            is None
        ), "the assistant waits for the transcript"
        fetch_id = fetch.id
    assert run_job(Picked(fetch_id, t.id, "fetch_media", 0), {"fetch_media": _handle_fetch_media})
    with service_session() as s:
        assert s.scalar(
            select(Job).where(
                Job.kind == "worker_turn", Job.payload["conversation_id"].astext == str(conv_id)
            )
        ), "then the assistant's turn is queued"
    return t, conv_id


def test_a_voice_note_is_transcribed_and_the_assistant_answers_what_was_said(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    t, conv_id = _voice_note(client, "Can someone service my boiler next week?", monkeypatch)
    llm = FakeLLM()
    with tenant_session(t.id) as s:
        run_turn(s, t, get_pack("hvac"), llm, conv_id)
    heard = llm.calls[0]["messages"][-1]["content"]
    assert "[Voice note]: Can someone service my boiler next week?" in heard

    owner = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
    view = client.get(f"/conversations/{conv_id}", headers=owner).json()
    entries = [e for m in view["messages"] for e in (m.get("media") or [])]
    assert entries[0]["transcript"] == "Can someone service my boiler next week?"
    assert entries[0]["content_type"].startswith("audio/ogg") and entries[0]["url"]


def test_an_emergency_said_out_loud_is_escalated_without_the_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    t, conv_id = _voice_note(client, "Help, I can smell gas in the kitchen", monkeypatch)

    class NoModel:
        def complete(self, **_: Any) -> Any:
            raise AssertionError("the emergency path needs no model")

    with tenant_session(t.id) as s:
        r = run_turn(s, t, get_pack("hvac"), NoModel(), conv_id)  # type: ignore[arg-type]
        assert r.emergency
        assert s.scalar(
            select(ActionProposal).where(
                ActionProposal.conversation_id == conv_id,
                ActionProposal.kind == "escalate_emergency",
            )
        )
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.status == "waiting_human"


def test_without_speech_to_text_the_assistant_asks_the_customer_to_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVAXIS_STT_PROVIDER", "none")
    get_settings.cache_clear()
    t, conv_id = _voice_note(client, "ignored", monkeypatch)
    monkeypatch.setenv("NOVAXIS_STT_PROVIDER", "none")
    get_settings.cache_clear()
    llm = FakeLLM()
    with tenant_session(t.id) as s:
        run_turn(s, t, get_pack("hvac"), llm, conv_id)
        msg = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "inbound"
            )
        )
        assert msg is not None and msg.media[0]["transcript_error"]
    assert UNHEARD in llm.calls[0]["messages"][-1]["content"]


def test_the_whisper_adapter_sends_the_audio_retries_and_fails_clearly() -> None:
    seen: list[httpx.Request] = []
    answers = iter([httpx.Response(503), httpx.Response(200, json={"text": " Hello there "})])

    def whisper(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return next(answers)

    stt = OpenAICompatSTT(
        "https://stt.test/v1", "key-1", "whisper-large-v3-turbo", "en", httpx.MockTransport(whisper)
    )
    t = stt.transcribe(OGG, "audio/ogg; codecs=opus", "voice-note.ogg")
    assert t.text == "Hello there" and t.model == "whisper-large-v3-turbo"
    assert len(seen) == 2, "a 503 is retried"
    req = seen[-1]
    assert str(req.url) == "https://stt.test/v1/audio/transcriptions"
    assert req.headers["authorization"] == "Bearer key-1"
    form = req.content
    assert b'name="model"' in form and b"whisper-large-v3-turbo" in form
    assert b'name="language"' in form and b'filename="voice-note.ogg"' in form and OGG in form

    bad = OpenAICompatSTT(
        "https://stt.test/v1", "", "m", transport=httpx.MockTransport(lambda r: httpx.Response(400))
    )
    with pytest.raises(TranscriptionError, match="400"):
        bad.transcribe(OGG, "audio/ogg", "v.ogg")


def test_a_failed_transcription_is_recorded_and_the_customer_asked_to_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        def transcribe(self, audio: bytes, content_type: str, filename: str) -> Any:
            raise TranscriptionError("speech-to-text unavailable")

    monkeypatch.setattr(media_mod, "build_stt", lambda: Broken())
    t, conv_id = _voice_note(client, "ignored", monkeypatch)
    with tenant_session(t.id) as s:
        msg = s.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.direction == "inbound"
            )
        )
        assert msg is not None
        assert "unavailable" in msg.media[0]["transcript_error"]
        assert media_mod.text_of(msg) == UNHEARD
