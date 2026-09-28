"""Object storage for customer media, under the tenant's prefix.

One small interface, three implementations: local disk for development and tests,
Postgres (`db`: survives restarts on hosts with no lasting disk, such as Vercel, and
needs no extra keys) and Supabase Storage. Keys are `<tenant_id>/<message_id>/<n>.<ext>`
so a tenant's files can be listed, exported or purged by prefix.

Access: files are never public. The local store is served by the API to
staff-level roles; the Supabase store hands out short-lived signed URLs.
"""

from __future__ import annotations

import mimetypes
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx
from sqlalchemy import Engine, text

from novaxis_core.settings import get_settings

_SAFE = re.compile(r"[^A-Za-z0-9._/-]")


class MediaRejectedError(ValueError):
    """Too large or a type we do not accept."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    content_type: str
    size: int


class BlobStore(Protocol):
    backend: str

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject: ...

    def get(self, key: str) -> tuple[bytes, str]: ...

    def url_for(self, key: str, expires_seconds: int = 3600) -> str: ...

    def delete(self, key: str) -> None: ...


def media_key(
    tenant_id: uuid.UUID,
    message_id: uuid.UUID,
    index: int,
    content_type: str,
    filename: str | None = None,
) -> str:
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()[:8]
    if not ext:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
    return _SAFE.sub("_", f"{tenant_id}/{message_id}/{index}{ext}")


def check_media(data: bytes, content_type: str) -> None:
    s = get_settings()
    if len(data) > s.media_max_bytes:
        raise MediaRejectedError(f"{len(data)} bytes exceeds the {s.media_max_bytes} byte limit")
    ct = content_type.split(";")[0].strip().lower()
    if not any(ct.startswith(a) for a in s.media_allowed_types):
        raise MediaRejectedError(f"content type {ct!r} is not accepted")


class LocalBlobStore:
    backend = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("key escapes the store root")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        (p.with_suffix(p.suffix + ".type")).write_text(content_type)
        return StoredObject(key=key, content_type=content_type, size=len(data))

    def get(self, key: str) -> tuple[bytes, str]:
        p = self._path(key)
        ct_file = p.with_suffix(p.suffix + ".type")
        ct = ct_file.read_text() if ct_file.exists() else "application/octet-stream"
        return p.read_bytes(), ct

    def url_for(self, key: str, expires_seconds: int = 3600) -> str:
        # Served by the API to authenticated staff (routes_media).
        return f"/media/{key}"

    def delete(self, key: str) -> None:
        p = self._path(key)
        p.unlink(missing_ok=True)
        p.with_suffix(p.suffix + ".type").unlink(missing_ok=True)


class SupabaseBlobStore:
    """Supabase Storage over its REST API. Bucket must exist and be private.
    Field names follow the Storage API as documented; verify against the project
    on first deploy [VERIFY]."""

    backend = "supabase"

    def __init__(
        self,
        base_url: str,
        service_key: str,
        bucket: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30, headers=self._headers)

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        with self._client() as c:
            r = c.post(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        r.raise_for_status()
        return StoredObject(key=key, content_type=content_type, size=len(data))

    def get(self, key: str) -> tuple[bytes, str]:
        with self._client() as c:
            r = c.get(f"{self.base_url}/storage/v1/object/{self.bucket}/{key}")
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "application/octet-stream")

    def url_for(self, key: str, expires_seconds: int = 3600) -> str:
        with self._client() as c:
            r = c.post(
                f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{key}",
                json={"expiresIn": expires_seconds},
            )
        r.raise_for_status()
        signed = str(r.json().get("signedURL", ""))
        return signed if signed.startswith("http") else f"{self.base_url}/storage/v1{signed}"

    def delete(self, key: str) -> None:
        with self._client() as c:
            r = c.delete(f"{self.base_url}/storage/v1/object/{self.bucket}/{key}")
        if r.status_code != 404:  # already gone is fine
            r.raise_for_status()


class DbBlobStore:
    """Files in the `media_objects` table (migration 0021). Served by the API like the
    local store. Fine for a pilot's photos and voice notes (10 MB cap each); move to
    object storage when the table grows past a few GB."""

    backend = "db"

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO media_objects (key, content_type, data) VALUES (:k, :ct, :d) "
                    "ON CONFLICT (key) DO UPDATE SET content_type = :ct, data = :d"
                ),
                {"k": key, "ct": content_type, "d": data},
            )
        return StoredObject(key=key, content_type=content_type, size=len(data))

    def get(self, key: str) -> tuple[bytes, str]:
        with self.engine.connect() as c:
            row = c.execute(
                text("SELECT data, content_type FROM media_objects WHERE key = :k"), {"k": key}
            ).first()
        if row is None:
            raise FileNotFoundError(key)
        return bytes(row[0]), str(row[1])

    def url_for(self, key: str, expires_seconds: int = 3600) -> str:
        return f"/media/{key}"

    def delete(self, key: str) -> None:
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM media_objects WHERE key = :k"), {"k": key})


@lru_cache(maxsize=1)
def get_store() -> BlobStore:
    s = get_settings()
    if s.storage_backend == "supabase":
        if not s.supabase_url or not s.supabase_service_key:
            raise RuntimeError(
                "supabase storage needs NOVAXIS_SUPABASE_URL and NOVAXIS_SUPABASE_SERVICE_KEY"
            )
        return SupabaseBlobStore(s.supabase_url, s.supabase_service_key, s.storage_bucket)
    if s.storage_backend == "db":
        from novaxis_db.session import get_engine  # core does not depend on db at import

        return DbBlobStore(get_engine())
    return LocalBlobStore(Path(s.storage_local_dir))


def reset_store_cache() -> None:
    get_store.cache_clear()
