"""Model metadata must be authenticated, scoped to the business, and secret-free."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from novaxis_api.auth import Principal, current_principal, db
from novaxis_api.main import create_app
from novaxis_core.settings import get_settings


def test_assistant_configuration_requires_authentication() -> None:
    client = TestClient(create_app())
    assert client.get("/settings/assistant").status_code == 401


@pytest.mark.parametrize("role", ["staff", "viewer"])
def test_assistant_configuration_requires_owner(role: str) -> None:
    app = create_app()
    app.dependency_overrides[current_principal] = lambda: Principal(
        uuid.uuid4(), uuid.uuid4(), role, "test@example.test"
    )
    app.dependency_overrides[db] = lambda: None
    assert TestClient(app).get("/settings/assistant").status_code == 403


@pytest.mark.parametrize("provider", ["fake", "openai_compatible"])
def test_config_distinguishes_observed_worker_from_api_and_omits_secrets(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    monkeypatch.setenv("NOVAXIS_LLM_PROVIDER", provider)
    monkeypatch.setenv("NOVAXIS_MODEL_WORKER", "configured-worker")
    monkeypatch.setenv("NOVAXIS_LLM_API_KEY", "do-not-expose-key")
    monkeypatch.setenv("NOVAXIS_LLM_BASE_URL", "https://private-provider.test/v1")
    get_settings.cache_clear()
    tenant_id = uuid.uuid4()
    queries = []

    class Session:
        def scalar(self, query):  # type: ignore[no-untyped-def]
            queries.append(query)
            return SimpleNamespace(
                model="observed-worker", created_at=datetime(2026, 10, 8, tzinfo=UTC)
            )

    app = create_app()
    app.dependency_overrides[current_principal] = lambda: Principal(
        uuid.uuid4(), tenant_id, "owner", "owner@example.test"
    )
    app.dependency_overrides[db] = lambda: Session()
    response = TestClient(app).get("/settings/assistant")
    assert response.status_code == 200
    data = response.json()
    assert data["models"]["responses"] == ("fake" if provider == "fake" else "configured-worker")
    assert data["latest_worker_call"]["model"] == "observed-worker"
    assert data["configuration_scope"] == "api_process"
    assert "do-not-expose-key" not in response.text
    assert "private-provider" not in response.text
    compiled = queries[0].compile()
    assert tenant_id in compiled.params.values()
    assert "llm.worker_turn" in compiled.params.values()


def test_assistant_configuration_with_no_usage_reports_unknown() -> None:
    app = create_app()
    app.dependency_overrides[current_principal] = lambda: Principal(
        uuid.uuid4(), uuid.uuid4(), "owner", "owner@example.test"
    )
    app.dependency_overrides[db] = lambda: SimpleNamespace(scalar=lambda query: None)
    response = TestClient(app).get("/settings/assistant")
    assert response.status_code == 200
    assert response.json()["latest_worker_call"] is None
