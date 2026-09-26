"""The job loop: pick, lease, run, complete or back off.

Picking uses `SELECT ... FOR UPDATE SKIP LOCKED` in the service session, because
the queue spans tenants. The job's work then runs inside `tenant_session`, so a
handler can only touch its own tenant's rows. A job that fails three times marks
its conversation `waiting_human` and stops retrying: a person, not a retry loop,
resolves a stuck customer.
"""

from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from novaxis_core.llm import LLMClient
from novaxis_core.models import AuditLog, Conversation, Job, Tenant
from novaxis_core.outbound import send_message
from novaxis_core.packspec import PackSpec
from novaxis_core.settings import get_settings
from novaxis_core.turn import run_turn
from novaxis_db.session import service_session, tenant_session

log = logging.getLogger("novaxis.worker")

Handler = Callable[[Session, Tenant, Job], None]


@dataclass(frozen=True)
class Picked:
    job_id: uuid.UUID
    tenant_id: uuid.UUID
    kind: str
    attempts: int


def default_worker_id() -> str:
    return get_settings().worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:6]}"


def reclaim_stale(session: Session, lease_seconds: int) -> int:
    """Jobs whose worker died mid-run go back to the queue."""
    cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
    result = session.execute(
        update(Job)
        .where(Job.state == "running", Job.locked_at < cutoff)
        .values(state="queued", locked_by=None, locked_at=None)
    )
    return result.rowcount or 0


def pick_one(session: Session, worker_id: str) -> Picked | None:
    """Lease the oldest runnable job, or None. Safe to call from many workers at once."""
    row = session.execute(
        text(
            """
            SELECT j.id, j.tenant_id, j.kind, j.attempts
            FROM jobs j JOIN tenants t ON t.id = j.tenant_id
            WHERE j.state = 'queued' AND j.run_after <= now()
              AND t.worker_enabled AND t.status IN ('active', 'trial')
            ORDER BY j.run_after, j.created_at
            LIMIT 1
            FOR UPDATE OF j SKIP LOCKED
            """
        )
    ).first()
    if row is None:
        return None
    session.execute(
        update(Job)
        .where(Job.id == row[0])
        .values(state="running", locked_by=worker_id, locked_at=datetime.now(UTC))
    )
    return Picked(job_id=row[0], tenant_id=row[1], kind=row[2], attempts=row[3])


def _handle_worker_turn(pack_for: Callable[[str], PackSpec], llm: LLMClient) -> Handler:
    def handler(session: Session, tenant: Tenant, job: Job) -> None:
        conv_id = uuid.UUID(job.payload["conversation_id"])
        run_turn(session, tenant, pack_for(tenant.pack_id), llm, conv_id)

    return handler


def _handle_send_message(session: Session, tenant: Tenant, job: Job) -> None:
    send_message(session, tenant, uuid.UUID(job.payload["message_id"]))


def build_handlers(pack_for: Callable[[str], PackSpec], llm: LLMClient) -> dict[str, Handler]:
    return {"worker_turn": _handle_worker_turn(pack_for, llm), "send_message": _handle_send_message}


def _fail(session: Session, job: Job, error: str, attempts: int) -> None:
    s = get_settings()
    job.attempts = attempts
    job.last_error = error[:2000]
    job.locked_by = None
    job.locked_at = None
    if attempts >= s.worker_max_attempts:
        job.state = "failed"
        conv_id = job.payload.get("conversation_id")
        if conv_id:
            conv = session.get(Conversation, uuid.UUID(conv_id))
            if conv is not None and conv.status != "closed":
                conv.status = "waiting_human"
        session.add(
            AuditLog(
                tenant_id=job.tenant_id,
                actor="worker",
                event="job.failed",
                subject_table="jobs",
                subject_id=job.id,
                diff={"kind": job.kind, "attempts": attempts, "error": error[:500]},
            )
        )
    else:
        delay = s.worker_backoff_seconds[min(attempts - 1, len(s.worker_backoff_seconds) - 1)]
        job.state = "queued"
        job.run_after = datetime.now(UTC) + timedelta(seconds=delay)


def run_job(picked: Picked, handlers: dict[str, Handler]) -> bool:
    """Run one leased job inside its tenant session. Returns True on success."""
    with tenant_session(picked.tenant_id) as session:
        job = session.get(Job, picked.job_id)
        tenant = session.get(Tenant, picked.tenant_id)
        if job is None or tenant is None:
            log.error("job %s vanished after lease", picked.job_id)
            return False
        handler = handlers.get(picked.kind)
        try:
            if handler is None:
                raise LookupError(f"no handler for job kind {picked.kind!r}")
            handler(session, tenant, job)
            job.state = "done"
            job.locked_by = None
            job.locked_at = None
            return True
        except Exception as exc:  # noqa: BLE001 - any failure backs the job off
            # Undo the handler's partial work, keep the job row update.
            session.rollback()
            job = session.get(Job, picked.job_id)
            if job is not None:
                _fail(session, job, f"{type(exc).__name__}: {exc}", picked.attempts + 1)
            log.warning("job %s failed attempt %d: %s", picked.job_id, picked.attempts + 1, exc)
            return False


def tick(handlers: dict[str, Handler], worker_id: str) -> bool:
    """One pass: reclaim stale leases, pick one job, run it. Returns True if a job ran."""
    s = get_settings()
    if not s.worker_enabled:
        return False
    with service_session() as session:
        reclaim_stale(session, s.worker_lease_seconds)
        picked = pick_one(session, worker_id)
    if picked is None:
        return False
    run_job(picked, handlers)
    return True


def drain(handlers: dict[str, Handler], worker_id: str, limit: int = 1000) -> int:
    """Run jobs until the queue is empty. For tests and `--once`."""
    n = 0
    while n < limit and tick(handlers, worker_id):
        n += 1
    return n


def queued_count(session: Session) -> int:
    return len(list(session.scalars(select(Job.id).where(Job.state == "queued"))))
