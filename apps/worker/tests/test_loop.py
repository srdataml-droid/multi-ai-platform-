"""The job loop: lease, run, retry, fail to a human, never double-run, kill switches."""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM
from novaxis_core.models import AuditLog, Conversation, Job, Message, Tenant
from novaxis_core.settings import get_settings
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack
from novaxis_worker.loop import build_handlers, drain, pick_one, run_job, tick


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVAXIS_WORKER_BACKOFF_SECONDS", "[0, 0, 0]")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _enqueue(tenant: Tenant, body: str = "hello") -> uuid.UUID:
    visitor = uuid.uuid4().hex[:10]
    with tenant_session(tenant.id) as s:
        r = ingest(
            s,
            tenant,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{visitor}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=visitor,
                body=body,
            ),
        )
        assert r.job_id is not None
        return r.job_id


def _clear_queue() -> None:
    with service_session() as s:
        for j in s.scalars(select(Job).where(Job.state.in_(["queued", "running"]))):
            j.state = "done"


def test_worker_turn_job_runs_end_to_end(hvac: Tenant) -> None:
    _clear_queue()
    job_id = _enqueue(hvac, "boiler noise")
    handlers = build_handlers(
        get_pack, FakeLLM(default_text="Sorry to hear that, what's your postcode?")
    )
    assert drain(handlers, "w1") >= 1  # the turn, plus any roll-ups the timer enqueued
    with tenant_session(hvac.id) as s:
        job = s.get(Job, job_id)
        assert job is not None and job.state == "done" and job.locked_by is None
        conv = s.get(Conversation, uuid.UUID(job.payload["conversation_id"]))
        assert conv is not None
        outbound = list(
            s.scalars(
                select(Message).where(
                    Message.conversation_id == conv.id, Message.direction == "outbound"
                )
            )
        )
        assert len(outbound) == 1 and "postcode" in outbound[0].body


def test_failing_job_backs_off_then_hands_to_human(hvac: Tenant) -> None:
    _clear_queue()
    job_id = _enqueue(hvac)

    def boom(session, tenant, job):  # type: ignore[no-untyped-def]
        raise RuntimeError("model down")

    handlers = {"worker_turn": boom}
    for attempt in (1, 2):
        assert tick(handlers, "w1")
        with tenant_session(hvac.id) as s:
            job = s.get(Job, job_id)
            assert job is not None and job.state == "queued" and job.attempts == attempt
            assert "model down" in (job.last_error or "")
    assert tick(handlers, "w1")
    with tenant_session(hvac.id) as s:
        job = s.get(Job, job_id)
        assert job is not None and job.state == "failed" and job.attempts == 3
        conv = s.get(Conversation, uuid.UUID(job.payload["conversation_id"]))
        assert conv is not None and conv.status == "waiting_human"
        audit = s.scalar(
            select(AuditLog).where(AuditLog.event == "job.failed", AuditLog.subject_id == job_id)
        )
        assert audit is not None
    assert not tick(handlers, "w1"), "failed job is not picked again"


def test_two_workers_never_run_the_same_job(hvac: Tenant) -> None:
    _clear_queue()
    ids = {_enqueue(hvac) for _ in range(6)}
    seen: list[uuid.UUID] = []
    lock = threading.Lock()
    gate = threading.Barrier(2)

    def slow(session, tenant, job):  # type: ignore[no-untyped-def]
        with lock:
            seen.append(job.id)
        threading.Event().wait(0.05)

    handlers = {"worker_turn": slow}

    def work(wid: str) -> None:
        gate.wait()
        drain(handlers, wid)

    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(seen) == sorted(ids), "every job ran exactly once"
    assert len(seen) == len(set(seen))


def test_platform_kill_switch_picks_nothing(hvac: Tenant, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_queue()
    _enqueue(hvac)
    monkeypatch.setenv("NOVAXIS_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    assert not tick({"worker_turn": lambda *a: None}, "w1")
    with service_session() as s:
        assert s.scalar(select(Job).where(Job.state == "queued")) is not None


def test_tenant_kill_switch_defers_its_jobs(hvac: Tenant) -> None:
    _clear_queue()
    _enqueue(hvac)
    with service_session() as s:
        t = s.get(Tenant, hvac.id)
        assert t is not None
        t.worker_enabled = False
    try:
        with service_session() as s:
            assert pick_one(s, "w1") is None
    finally:
        with service_session() as s:
            t = s.get(Tenant, hvac.id)
            assert t is not None
            t.worker_enabled = True
    with service_session() as s:
        picked = pick_one(s, "w1")
        assert picked is not None
    assert run_job(picked, {"worker_turn": lambda *a: None})
