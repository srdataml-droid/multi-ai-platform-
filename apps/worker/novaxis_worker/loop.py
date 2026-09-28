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
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from novaxis_core.agent_webhooks import AGENT_EVENT_JOB, deliver
from novaxis_core.alerts import ALERT_JOB, alert_staff, needs_a_person
from novaxis_core.approvals import expire_stale_proposals
from novaxis_core.billing import (
    REPORT_USAGE_KIND,
    StripeClient,
    enqueue_usage_reports,
    report_daily_usage,
    trial_block_reason,
)
from novaxis_core.bridge import EMAIL_JOB as BRIDGE_EMAIL_KIND
from novaxis_core.bridge import send_ticket_email
from novaxis_core.llm import LLMClient
from novaxis_core.media import fetch_media
from novaxis_core.metrics import ROLLUP_KIND, enqueue_rollups, rollup_recent
from novaxis_core.models import AuditLog, Conversation, Job, Message, Tenant
from novaxis_core.notify import notify_staff
from novaxis_core.outbound import ReplyWindowClosedError, send_message
from novaxis_core.packspec import PackSpec
from novaxis_core.privacy import PURGE_KIND, enqueue_purges, purge_expired
from novaxis_core.settings import get_settings
from novaxis_core.turn import run_turn
from novaxis_core.workflows import run_step
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
        blocked = trial_block_reason(session, tenant, datetime.now(UTC))
        run_turn(session, tenant, pack_for(tenant.pack_id), llm, conv_id, blocked_reason=blocked)

    return handler


def _handle_send_message(session: Session, tenant: Tenant, job: Job) -> None:
    msg_id = uuid.UUID(job.payload["message_id"])
    try:
        send_message(session, tenant, msg_id)
    except ReplyWindowClosedError as exc:
        # Retrying cannot open WhatsApp's window; only the customer or a person can.
        msg = session.get(Message, msg_id)
        conv = session.get(Conversation, msg.conversation_id) if msg else None
        if conv is not None:
            if conv.status not in ("waiting_human", "closed"):
                conv.status = "waiting_human"
            needs_a_person(session, tenant.id, conv.id)
        job.last_error = f"to a person: {exc}"[:2000]


def _handle_notify_staff(session: Session, tenant: Tenant, job: Job) -> None:
    notify_staff(session, tenant, uuid.UUID(job.payload["proposal_id"]))


def _handle_workflow_step(pack_for: Callable[[str], PackSpec]) -> Handler:
    def handler(session: Session, tenant: Tenant, job: Job) -> None:
        blocked = trial_block_reason(session, tenant, datetime.now(UTC))
        if blocked:
            job.last_error = f"skipped: {blocked}"
            return
        outcome = run_step(session, tenant, pack_for(tenant.pack_id), job)
        job.last_error = outcome  # the outcome word is useful in the job log

    return handler


def _handle_rollup(session: Session, tenant: Tenant, job: Job) -> None:
    rollup_recent(session, tenant)


def _handle_fetch_media(session: Session, tenant: Tenant, job: Job) -> None:
    fetch_media(session, tenant, uuid.UUID(job.payload["message_id"]))


def _handle_report_usage(session: Session, tenant: Tenant, job: Job) -> None:
    n = report_daily_usage(session, tenant, StripeClient(), date.fromisoformat(job.payload["day"]))
    job.last_error = f"reported {n}"


def _handle_bridge_email(session: Session, tenant: Tenant, job: Job) -> None:
    job.last_error = send_ticket_email(session, tenant, uuid.UUID(job.payload["ticket_id"]))


def _handle_alert(session: Session, tenant: Tenant, job: Job) -> None:
    p = job.payload
    n = alert_staff(session, tenant, str(p["title"]), str(p["body"]), str(p["url"]))
    job.last_error = f"delivered {n}"


def _handle_agent_event(session: Session, tenant: Tenant, job: Job) -> None:
    job.last_error = deliver(session, tenant, job)


def _handle_purge(session: Session, tenant: Tenant, job: Job) -> None:
    # Erasure needs the service role (messages are append-only for the app role); every
    # statement inside is filtered by this tenant.
    with service_session() as svc:
        t = svc.get(Tenant, tenant.id)
        n = purge_expired(svc, t) if t is not None else 0
    job.last_error = f"erased {n}"


def build_handlers(pack_for: Callable[[str], PackSpec], llm: LLMClient) -> dict[str, Handler]:
    return {
        ROLLUP_KIND: _handle_rollup,
        REPORT_USAGE_KIND: _handle_report_usage,
        BRIDGE_EMAIL_KIND: _handle_bridge_email,
        ALERT_JOB: _handle_alert,
        AGENT_EVENT_JOB: _handle_agent_event,
        PURGE_KIND: _handle_purge,
        "fetch_media": _handle_fetch_media,
        "worker_turn": _handle_worker_turn(pack_for, llm),
        "send_message": _handle_send_message,
        "notify_staff": _handle_notify_staff,
        "workflow_step": _handle_workflow_step(pack_for),
    }


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
                needs_a_person(session, job.tenant_id, conv.id)
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


_last_periodic: datetime | None = None


def periodic(session: Session) -> None:
    """Things that happen on a timer rather than on a message: metrics roll-ups."""
    global _last_periodic
    now = datetime.now(UTC)
    if _last_periodic and now - _last_periodic < timedelta(minutes=5):
        return
    _last_periodic = now
    ids = [
        t.id
        for t in session.scalars(
            select(Tenant).where(Tenant.status.in_(["active", "trial"]), Tenant.plan != "internal")
        )
    ]
    enqueue_rollups(session, ids)
    enqueue_usage_reports(session, now)
    expire_stale_proposals(session, now)
    enqueue_purges(session, ids)


def tick(handlers: dict[str, Handler], worker_id: str) -> bool:
    """One pass: reclaim stale leases, pick one job, run it. Returns True if a job ran."""
    s = get_settings()
    if not s.worker_enabled:
        return False
    with service_session() as session:
        reclaim_stale(session, s.worker_lease_seconds)
        if ROLLUP_KIND in handlers:
            periodic(session)
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
