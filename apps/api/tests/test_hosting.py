"""Serverless hosting: demo passcode login, internal endpoints, pooler engine, inline worker."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.main import create_app
from novaxis_core.models import Job, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import get_engine, normalise_url, service_session


@pytest.fixture
def env(migrated: str, monkeypatch: pytest.MonkeyPatch):
    with service_session(migrated) as s:
        seed(s)

    def set_env(**kv: str) -> TestClient:
        for k, v in kv.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield set_env
    get_settings.cache_clear()


def test_demo_passcode_gates_login_outside_local(env) -> None:  # type: ignore[no-untyped-def]
    c = env(NOVAXIS_ENV="production", NOVAXIS_DEMO_PASSCODE="open-sesame-123")
    assert c.get("/auth/config").json()["mode"] == "demo"
    assert c.post("/auth/dev-login", json={"email": "owner@demo-hvac.test"}).status_code == 401
    assert (
        c.post(
            "/auth/dev-login", json={"email": "owner@demo-hvac.test", "passcode": "nope"}
        ).status_code
        == 401
    )
    ok = c.post(
        "/auth/dev-login", json={"email": "owner@demo-hvac.test", "passcode": "open-sesame-123"}
    )
    assert ok.status_code == 200 and ok.json()["role"] == "owner"


def test_no_passcode_means_no_login_in_production(env) -> None:  # type: ignore[no-untyped-def]
    c = env(NOVAXIS_ENV="production", NOVAXIS_DEMO_PASSCODE="")
    assert c.get("/auth/config").json()["mode"] == "none"
    assert c.post("/auth/dev-login", json={"email": "owner@demo-hvac.test"}).status_code == 404


def test_internal_endpoints_need_the_secret(env) -> None:  # type: ignore[no-untyped-def]
    c = env(NOVAXIS_CRON_SECRET="")
    assert c.post("/internal/tick").status_code == 404, (
        "no secret configured: endpoints do not exist"
    )
    c = env(NOVAXIS_CRON_SECRET="s3cret-value")
    assert c.post("/internal/tick").status_code == 401
    assert c.post("/internal/tick", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = c.post("/internal/tick", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200 and "jobs_run" in r.json()
    r = c.post("/internal/seed", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200 and "demo-hvac" in r.json()["tenants"]
    r = c.post("/internal/migrate", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200


def test_inline_worker_answers_a_webchat_message_before_responding(env) -> None:  # type: ignore[no-untyped-def]
    c = env(NOVAXIS_INLINE_WORKER="true", NOVAXIS_LLM_PROVIDER="fake")
    from novaxis_api import inline_worker

    inline_worker._handlers.cache_clear()
    r = c.post("/inbound/webchat/demo-hvac", json={"body": f"hello {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200
    msgs = c.get(
        "/inbound/webchat/demo-hvac/messages", params={"visitor_token": r.json()["visitor_token"]}
    ).json()
    assert any(m["direction"] == "outbound" for m in msgs["messages"]), (
        "reply exists without a worker process"
    )
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        job = s.scalar(
            select(Job).where(
                Job.payload["conversation_id"].astext == r.json()["conversation_id"],
                Job.kind == "worker_turn",
            )
        )
        assert job is not None and job.state == "done"


def test_pooler_engine_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    assert normalise_url("postgres://u:p@h:6543/db") == "postgresql+psycopg://u:p@h:6543/db"
    assert normalise_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    monkeypatch.setenv("NOVAXIS_DB_POOLER", "true")
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        eng = get_engine("postgresql+psycopg://u:p@localhost:1/db")
        assert type(eng.pool).__name__ == "NullPool"
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_vercel_entrypoint_imports_the_app() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "vercel_app.py"
    spec = importlib.util.spec_from_file_location("vercel_app", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.app.title == "Novaxis AI Worker API"


def test_widget_routes_answer_cross_origin_and_nothing_else_does(env) -> None:  # type: ignore[no-untyped-def]
    c = env()
    site = {"Origin": "https://a-plumber.co.uk"}
    pre = c.options(
        "/inbound/webchat/demo-hvac",
        headers={
            **site,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert pre.status_code == 204
    assert pre.headers["access-control-allow-origin"] == "*"
    assert "POST" in pre.headers["access-control-allow-methods"]
    assert "content-type" in pre.headers["access-control-allow-headers"]
    sent = c.post("/inbound/webchat/demo-hvac", json={"body": "hello"}, headers=site)
    assert sent.status_code == 200 and sent.headers["access-control-allow-origin"] == "*"
    polled = c.get(
        "/inbound/webchat/demo-hvac/messages",
        params={"visitor_token": sent.json()["visitor_token"]},
        headers=site,
    )
    assert polled.headers["access-control-allow-origin"] == "*"
    # Staff routes stay same-origin only.
    assert "access-control-allow-origin" not in c.get("/health", headers=site).headers
    assert "access-control-allow-origin" not in c.get("/me", headers=site).headers


def test_timer_sees_a_broken_loop_as_a_failure(env, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from novaxis_api import inline_worker

    c = env(NOVAXIS_CRON_SECRET="s3cret-value")

    def broken(*_a: object, **_k: object) -> bool:
        raise RuntimeError("database went away")

    monkeypatch.setattr(inline_worker, "tick", broken)
    r = c.post("/internal/tick", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 500 and "RuntimeError" in r.json()["detail"]
    # After a customer's request the same failure is swallowed: the message is still accepted.
    assert inline_worker.drain_for(budget_seconds=1) == 0


def test_deep_health_reports_what_needs_a_person(env) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    c = env()
    r = c.get("/health/deep")
    body = r.json()
    assert body["checks"]["database"] is True and body["checks"]["schema_current"] is True
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        stuck = Job(
            tenant_id=t.id,
            kind="noop",
            payload={},
            run_after=datetime.now(UTC) - timedelta(hours=1),
        )
        s.add(stuck)
        s.flush()
        stuck_id = stuck.id
    try:
        r = c.get("/health/deep")
        assert r.status_code == 503 and r.json()["checks"]["stuck_jobs"] >= 1
    finally:
        with service_session() as s:
            s.get(Job, stuck_id).state = "done"  # type: ignore[union-attr]
