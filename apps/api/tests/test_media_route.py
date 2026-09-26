from __future__ import annotations

import base64
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.channels import Media, NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import Tenant, User
from novaxis_core.settings import get_settings
from novaxis_core.storage import reset_store_cache
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def client(migrated: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NOVAXIS_STORAGE_LOCAL_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    reset_store_cache()
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-restoration"))
        assert t is not None
        if s.scalar(select(User).where(User.auth_subject == "dev|viewer@demo-restoration")) is None:
            s.add(
                User(
                    tenant_id=t.id,
                    auth_subject="dev|viewer@demo-restoration",
                    email="v@demo-restoration.test",
                    role="viewer",
                )
            )
    yield TestClient(create_app())
    get_settings.cache_clear()
    reset_store_cache()


def _ingest_photo() -> tuple[uuid.UUID, str]:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-restoration"))
        assert t is not None
        s.expunge(t)
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="email",
                provider_ref=f"pm-{uuid.uuid4().hex[:8]}",
                tenant_ref="demo-restoration@inbound.novaxis.test",
                sender_email="o@example.com",
                body="photo",
                media=[
                    Media(
                        url="postmark-attachment:a.png",
                        content_type="image/png",
                        filename="a.png",
                        inline_base64=base64.b64encode(PNG).decode(),
                    )
                ],
            ),
        )
        from novaxis_core.models import Message

        msg = s.get(Message, r.message_id)
        assert msg is not None
        return r.conversation_id, msg.media[0]["stored_key"]


def test_conversation_lists_media_and_staff_can_open_it(client: TestClient) -> None:
    conv_id, key = _ingest_photo()
    owner = {"Authorization": f"Bearer {mint('dev|owner@demo-restoration')}"}
    conv = client.get(f"/conversations/{conv_id}", headers=owner).json()
    media = conv["messages"][0]["media"]
    assert media[0]["url"] == f"/media/{key}" and media[0]["content_type"] == "image/png"
    r = client.get(media[0]["url"], headers=owner)
    assert (
        r.status_code == 200
        and r.content == PNG
        and r.headers["content-type"].startswith("image/png")
    )


def test_viewer_and_other_tenant_cannot_open_media(client: TestClient) -> None:
    _, key = _ingest_photo()
    viewer = {"Authorization": f"Bearer {mint('dev|viewer@demo-restoration')}"}
    assert client.get(f"/media/{key}", headers=viewer).status_code == 403
    other = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
    assert client.get(f"/media/{key}", headers=other).status_code == 404
