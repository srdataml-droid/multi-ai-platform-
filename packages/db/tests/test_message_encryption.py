"""Message text at rest: what customers and the assistant write, voice-note transcripts and
conversation summaries are stored encrypted and read as plain text by the application.
A database dump, a backup or someone with SQL access sees ciphertext."""

from __future__ import annotations

import json
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import select, text

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.media import media_view, text_of
from novaxis_core.models import Conversation, Message, Tenant
from novaxis_core.sensitive import PREFIX, decrypt, encrypt, reset_key_cache
from novaxis_core.settings import get_settings
from novaxis_db import migrate
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


def _tenant(url: str) -> Tenant:
    with service_session(url) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        s.expunge(t)
        return t


def _say(t: Tenant, body: str) -> tuple[uuid.UUID, uuid.UUID]:
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                body=body,
            ),
        )
        return r.conversation_id, r.message_id


def _raw(sql: str, **params: object) -> object:
    with service_session() as s:
        return s.execute(text(sql), params).scalar()


def test_message_text_is_ciphertext_in_the_database(migrated: str) -> None:
    t = _tenant(migrated)
    conv_id, msg_id = _say(t, "I have asthma and my tooth hurts")
    raw = str(_raw("SELECT body FROM messages WHERE id = :i", i=msg_id))
    assert raw.startswith(PREFIX) and "asthma" not in raw
    with tenant_session(t.id) as s:
        m = s.get(Message, msg_id)
        assert m is not None and m.body == "I have asthma and my tooth hurts"
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        conv.summary = "Patient with asthma, toothache"
    raw_summary = str(_raw("SELECT summary FROM conversations WHERE id = :i", i=conv_id))
    assert raw_summary.startswith(PREFIX) and "asthma" not in raw_summary
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None and conv.summary == "Patient with asthma, toothache"


def test_voice_note_transcripts_are_encrypted_and_read_back(migrated: str) -> None:
    t = _tenant(migrated)
    _, msg_id = _say(t, "")
    with tenant_session(t.id) as s:
        m = s.get(Message, msg_id)
        assert m is not None
        m.media = [{"audio": True, "transcript": encrypt("my gums are bleeding")}]
    raw = str(_raw("SELECT media::text FROM messages WHERE id = :i", i=msg_id))
    assert "bleeding" not in raw
    with tenant_session(t.id) as s:
        m = s.get(Message, msg_id)
        assert m is not None
        assert "my gums are bleeding" in text_of(m)
        assert media_view(m.media)[0]["transcript"] == "my gums are bleeding"


def test_the_migration_encrypts_what_was_stored_before(migrated: str) -> None:
    t = _tenant(migrated)
    conv_id, msg_id = _say(t, "placeholder")
    migrate.downgrade(migrated, "0021")  # as before this change: plain text
    try:
        with service_session() as s:
            s.execute(
                text(
                    "UPDATE messages SET body = 'old plain text', media = CAST(:m AS jsonb) "
                    "WHERE id = :i"
                ),
                {"i": msg_id, "m": json.dumps([{"audio": True, "transcript": "old words"}])},
            )
            s.execute(
                text("UPDATE conversations SET summary = 'old summary' WHERE id = :i"),
                {"i": conv_id},
            )
    finally:
        migrate.upgrade(migrated, "head")
    body = str(_raw("SELECT body FROM messages WHERE id = :i", i=msg_id))
    media = str(_raw("SELECT media::text FROM messages WHERE id = :i", i=msg_id))
    summary = str(_raw("SELECT summary FROM conversations WHERE id = :i", i=conv_id))
    assert body.startswith(PREFIX) and decrypt(body) == "old plain text"
    assert "old words" not in media
    assert summary.startswith(PREFIX) and decrypt(summary) == "old summary"
    with tenant_session(t.id) as s:
        m = s.get(Message, msg_id)
        assert m is not None and m.body == "old plain text"


def test_keys_can_be_rotated_without_losing_old_messages(migrated: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("NOVAXIS_SENSITIVE_FIELDS_KEY", old)
    get_settings.cache_clear()
    reset_key_cache()
    try:
        sealed = encrypt("written under the old key")
        monkeypatch.setenv("NOVAXIS_SENSITIVE_FIELDS_KEY", f"{new},{old}")
        get_settings.cache_clear()
        reset_key_cache()
        assert decrypt(sealed) == "written under the old key", "old key still reads"
        fresh = encrypt("written under the new key")
        monkeypatch.setenv("NOVAXIS_SENSITIVE_FIELDS_KEY", new)
        get_settings.cache_clear()
        reset_key_cache()
        assert decrypt(fresh) == "written under the new key", "new writes use the new key"
    finally:
        monkeypatch.delenv("NOVAXIS_SENSITIVE_FIELDS_KEY")
        get_settings.cache_clear()
        reset_key_cache()


def _keys(monkeypatch, current: str, nxt: str = "") -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("NOVAXIS_SENSITIVE_FIELDS_KEY", current)
    monkeypatch.setenv("NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT", nxt)
    get_settings.cache_clear()
    reset_key_cache()


def _derived() -> str:
    import base64
    import hashlib

    raw = hashlib.sha256(f"sensitive:{get_settings().jwt_secret}".encode()).digest()
    return base64.urlsafe_b64encode(raw).decode()


def _rekey_until_done(budget: int) -> int:
    from novaxis_db.rekey import rekey

    passes = 0
    while True:
        passes += 1
        with service_session() as s:
            r = rekey(s, budget=budget)
        if r["remaining"] == 0:
            return passes
        assert passes < 500


def test_changing_to_a_key_you_saved_moves_every_encrypted_value(
    migrated: str, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The deployed key cannot be read back from the host, so a key the founder has saved
    becomes NEXT; the job moves everything to it in small passes; then it is the only key."""
    t = _tenant(migrated)
    conv_id, msg_id = _say(t, "private words before the change")
    with tenant_session(t.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        conv.summary = "a summary before the change"
        conv.extracted = {**conv.extracted, "symptoms": encrypt("toothache")}
    today = _derived()
    saved = Fernet.generate_key().decode()
    try:
        _keys(monkeypatch, today, nxt=saved)
        assert _rekey_until_done(budget=3) > 1, "done in passes, each within a request"
        _keys(monkeypatch, saved)  # the saved key alone
        with tenant_session(t.id) as s:
            m = s.get(Message, msg_id)
            conv = s.get(Conversation, conv_id)
            assert m is not None and m.body == "private words before the change"
            assert conv is not None and conv.summary == "a summary before the change"
            assert decrypt(conv.extracted["symptoms"]) == "toothache"
    finally:
        # Put the test database back under the default key for the tests that follow.
        _keys(monkeypatch, saved, nxt=today)
        _rekey_until_done(budget=5000)
        monkeypatch.delenv("NOVAXIS_SENSITIVE_FIELDS_KEY")
        monkeypatch.delenv("NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT")
        get_settings.cache_clear()
        reset_key_cache()
