"""Attachments: inline stored during ingest, URL media fetched by a job with provider auth."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from novaxis_core.channels import Media, NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.media import fetch_media, media_view
from novaxis_core.models import Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_core.storage import get_store, reset_store_cache
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVAXIS_STORAGE_LOCAL_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("NOVAXIS_TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("NOVAXIS_TWILIO_AUTH_TOKEN", "tok")
    get_settings.cache_clear()
    reset_store_cache()
    yield
    get_settings.cache_clear()
    reset_store_cache()


@pytest.fixture
def resto(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-restoration"))
        assert t is not None
        s.expunge(t)
        return t


def test_inline_attachment_is_stored_during_ingest(resto: Tenant) -> None:
    inbound = NormalisedInbound(
        channel="email",
        provider_ref=f"pm-{uuid.uuid4().hex[:8]}",
        tenant_ref="demo-restoration@inbound.novaxis.test",
        sender_email="owner@example.com",
        body="photo attached",
        media=[
            Media(
                url="postmark-attachment:kitchen.png",
                content_type="image/png",
                filename="kitchen.png",
                inline_base64=base64.b64encode(PNG).decode(),
            )
        ],
    )
    with tenant_session(resto.id) as s:
        r = ingest(s, resto, inbound)
        msg = s.get(Message, r.message_id)
        assert msg is not None and len(msg.media) == 1
        entry = msg.media[0]
        assert entry["stored_key"].startswith(f"{resto.id}/{msg.id}/0") and entry[
            "stored_key"
        ].endswith(".png")
        assert entry["size"] == len(PNG) and "inline_base64" not in entry
        assert (
            s.scalar(
                select(Job).where(
                    Job.kind == "fetch_media", Job.payload["message_id"].astext == str(msg.id)
                )
            )
            is None
        )
        data, ct = get_store().get(entry["stored_key"])
        assert data == PNG and ct == "image/png"
        view = media_view(msg.media)
        assert view[0]["url"] == f"/media/{entry['stored_key']}" and view[0]["error"] is None


def test_url_media_is_fetched_by_job_with_twilio_auth(resto: Tenant) -> None:
    inbound = NormalisedInbound(
        channel="twilio_sms",
        provider_ref=f"MM{uuid.uuid4().hex[:8]}",
        tenant_ref="+15005550008",
        sender_phone="+447700900999",
        body="",
        media=[
            Media(
                url="https://api.twilio.com/2010-04-01/Accounts/AC/Messages/MM/Media/ME1",
                content_type="image/jpeg",
            )
        ],
    )
    with tenant_session(resto.id) as s:
        r = ingest(s, resto, inbound)
        job = s.scalar(
            select(Job).where(
                Job.kind == "fetch_media", Job.payload["message_id"].astext == str(r.message_id)
            )
        )
        assert job is not None, "URL media enqueues a fetch"
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/jpeg"})

    with tenant_session(resto.id) as s:
        n = fetch_media(s, resto, r.message_id, transport=httpx.MockTransport(handler))
        assert n == 1
        msg = s.get(Message, r.message_id)
        assert (
            msg is not None
            and msg.media[0]["stored_key"].endswith(".jpg")
            and msg.media[0]["size"] == len(PNG)
        )
    assert seen[0].headers["authorization"].startswith("Basic "), "Twilio media needs account auth"
    assert base64.b64decode(seen[0].headers["authorization"].split()[1]) == b"ACtest:tok"


def test_rejected_media_records_error_not_crash(resto: Tenant) -> None:
    inbound = NormalisedInbound(
        channel="email",
        provider_ref=f"pm-{uuid.uuid4().hex[:8]}",
        tenant_ref="demo-restoration@inbound.novaxis.test",
        sender_email="owner@example.com",
        body="exe attached",
        media=[
            Media(
                url="postmark-attachment:x.exe",
                content_type="application/x-msdownload",
                filename="x.exe",
                inline_base64=base64.b64encode(b"MZ").decode(),
            )
        ],
    )
    with tenant_session(resto.id) as s:
        r = ingest(s, resto, inbound)
        msg = s.get(Message, r.message_id)
        assert (
            msg is not None
            and "not accepted" in msg.media[0]["error"]
            and msg.media[0].get("stored_key") is None
        )
        assert r.job_id is not None, "the message itself still reaches the worker"


def test_fetch_failure_is_recorded(resto: Tenant) -> None:
    inbound = NormalisedInbound(
        channel="twilio_sms",
        provider_ref=f"MM{uuid.uuid4().hex[:8]}",
        tenant_ref="+15005550008",
        sender_phone="+447700900998",
        body="pic",
        media=[Media(url="https://api.twilio.com/x/ME2", content_type="image/jpeg")],
    )
    with tenant_session(resto.id) as s:
        r = ingest(s, resto, inbound)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with tenant_session(resto.id) as s:
        assert fetch_media(s, resto, r.message_id, transport=httpx.MockTransport(handler)) == 0
        msg = s.get(Message, r.message_id)
        assert msg is not None and "HTTPStatusError" in msg.media[0]["error"]
