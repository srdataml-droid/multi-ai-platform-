from __future__ import annotations

from fastapi.testclient import TestClient

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_db.seed import seed
from novaxis_db.session import service_session


def _client(migrated: str) -> TestClient:
    with service_session(migrated) as s:
        seed(s)
    return TestClient(create_app())


def test_me_returns_own_tenant(migrated: str) -> None:
    client = _client(migrated)
    r = client.get("/me", headers={"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "owner"
    assert body["tenant"]["slug"] == "demo-hvac"
    assert body["tenant"]["pack_id"] == "hvac"


def test_me_without_token_is_401(migrated: str) -> None:
    assert _client(migrated).get("/me").status_code == 401


def test_me_with_forged_token_is_401(migrated: str) -> None:
    import jwt

    forged = jwt.encode(
        {"sub": "dev|owner@demo-hvac", "aud": "authenticated"},
        "wrong-secret-that-is-long-enough-for-hs256-x",
        "HS256",
    )
    r = _client(migrated).get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_me_unknown_subject_is_403(migrated: str) -> None:
    r = _client(migrated).get("/me", headers={"Authorization": f"Bearer {mint('dev|nobody')}"})
    assert r.status_code == 403
