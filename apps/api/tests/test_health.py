from fastapi.testclient import TestClient

from novaxis_api.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_has_commit() -> None:
    client = TestClient(create_app())
    body = client.get("/version").json()
    assert "version" in body and "commit" in body
