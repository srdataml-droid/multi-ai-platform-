from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from novaxis_core.settings import get_settings
from novaxis_core.storage import (
    LocalBlobStore,
    MediaRejectedError,
    SupabaseBlobStore,
    check_media,
    media_key,
)


def test_media_key_is_tenant_prefixed_and_safe() -> None:
    t, m = uuid.uuid4(), uuid.uuid4()
    key = media_key(t, m, 0, "image/jpeg", "../evil name.JPG")
    assert key.startswith(f"{t}/{m}/0") and key.endswith(".jpg") and ".." not in key.split("/")[-1]
    assert media_key(t, m, 1, "application/pdf").endswith(".pdf")
    assert media_key(t, m, 2, "application/x-unknown").endswith(".bin")


def test_check_media_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_MEDIA_MAX_BYTES", "10")
    get_settings.cache_clear()
    try:
        check_media(b"123", "image/png")
        with pytest.raises(MediaRejectedError, match="exceeds"):
            check_media(b"x" * 11, "image/png")
        with pytest.raises(MediaRejectedError, match="not accepted"):
            check_media(b"x", "application/x-msdownload")
    finally:
        get_settings.cache_clear()


def test_local_store_roundtrip_and_escape_guard(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path)
    obj = store.put("t/m/0.png", b"\x89PNG", "image/png")
    assert obj.size == 4
    data, ct = store.get("t/m/0.png")
    assert data == b"\x89PNG" and ct == "image/png"
    assert store.url_for("t/m/0.png") == "/media/t/m/0.png"
    with pytest.raises(ValueError):
        store.put("../outside.txt", b"x", "text/plain")


def test_supabase_store_calls_storage_api() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "POST" and "/object/sign/" in req.url.path:
            return httpx.Response(200, json={"signedURL": "/object/sign/media/t/m/0.png?token=abc"})
        if req.method == "POST":
            return httpx.Response(200, json={"Key": "media/t/m/0.png"})
        return httpx.Response(200, content=b"data", headers={"content-type": "image/png"})

    store = SupabaseBlobStore(
        "https://proj.supabase.co", "service-key", "media", transport=httpx.MockTransport(handler)
    )
    store.put("t/m/0.png", b"data", "image/png")
    assert seen[0].url.path == "/storage/v1/object/media/t/m/0.png"
    assert (
        seen[0].headers["authorization"] == "Bearer service-key"
        and seen[0].headers["content-type"] == "image/png"
    )
    assert store.get("t/m/0.png") == (b"data", "image/png")
    url = store.url_for("t/m/0.png")
    assert url == "https://proj.supabase.co/storage/v1/object/sign/media/t/m/0.png?token=abc"
    assert json.loads(seen[2].content)["expiresIn"] == 3600
