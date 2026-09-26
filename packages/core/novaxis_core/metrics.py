"""Hourly roll-up into metrics_daily. The dashboard reads only this table, never
the raw rows, so analytics never touch sensitive fields and stay fast."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novaxis_core.models import ActionProposal, Conversation, Job, Message, MetricsDaily, Tenant

ROLLUP_KIND = "rollup_metrics"


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, UTC)
    return start, start + timedelta(days=1)


def rollup_day(session: Session, tenant: Tenant, day: date) -> list[MetricsDaily]:
    """Recompute one tenant-day from raw rows. Idempotent: rows are replaced."""
    start, end = _day_bounds(day)
    inbound = (
        select(Message.channel, Message.conversation_id, Message.created_at)
        .where(
            Message.direction == "inbound", Message.created_at >= start, Message.created_at < end
        )
        .subquery()
    )
    channels = [r[0] for r in session.execute(select(inbound.c.channel).distinct())]
    out: list[MetricsDaily] = []
    for channel in channels:
        n_inbound = (
            session.scalar(
                select(func.count()).select_from(inbound).where(inbound.c.channel == channel)
            )
            or 0
        )
        # answered under 10s: an outbound worker message within 10s of an inbound one
        fast = 0
        for _, conv_id, at in session.execute(select(inbound).where(inbound.c.channel == channel)):
            reply = session.scalar(
                select(Message.created_at)
                .where(
                    Message.conversation_id == conv_id,
                    Message.direction == "outbound",
                    Message.author == "worker",
                    Message.created_at > at,
                )
                .order_by(Message.created_at)
                .limit(1)
            )
            if reply is not None and (reply - at).total_seconds() <= 10:
                fast += 1
        conv_ids = [
            r[0]
            for r in session.execute(
                select(inbound.c.conversation_id).where(inbound.c.channel == channel).distinct()
            )
        ]
        proposals = (
            list(
                session.scalars(
                    select(ActionProposal).where(
                        ActionProposal.conversation_id.in_(conv_ids),
                        ActionProposal.created_at >= start,
                        ActionProposal.created_at < end,
                    )
                )
            )
            if conv_ids
            else []
        )
        bookings_proposed = sum(
            1
            for p in proposals
            if p.kind == "propose_appointment" and p.state not in ("rejected", "failed")
        )
        bookings_approved = sum(
            1 for p in proposals if p.kind == "confirm_appointment" and p.state == "executed"
        )
        escalations = sum(1 for p in proposals if p.kind == "escalate_emergency")
        takeovers = (
            session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.id.in_(conv_ids),
                    Conversation.takeover_at >= start,
                    Conversation.takeover_at < end,
                )
            )
            if conv_ids
            else 0
        ) or 0
        intake_done = sum(1 for p in proposals if p.kind == "propose_appointment")
        existing = session.scalar(
            select(MetricsDaily).where(
                MetricsDaily.day == start.replace(tzinfo=None), MetricsDaily.channel == channel
            )
        )
        row = existing or MetricsDaily(
            tenant_id=tenant.id, day=start.replace(tzinfo=None), channel=channel
        )
        row.inbound = n_inbound
        row.answered_under_10s = fast
        row.intake_completed = intake_done
        row.bookings_proposed = bookings_proposed
        row.bookings_approved = bookings_approved
        row.escalations = escalations
        row.human_takeovers = takeovers
        session.add(row)
        out.append(row)
    session.flush()
    return out


def rollup_recent(session: Session, tenant: Tenant, days: int = 2) -> int:
    today = datetime.now(UTC).date()
    n = 0
    for i in range(days):
        n += len(rollup_day(session, tenant, today - timedelta(days=i)))
    return n


def enqueue_rollups(
    session: Session, tenant_ids: list[uuid.UUID], min_interval: timedelta = timedelta(hours=1)
) -> int:
    """Called by the worker on a timer with a service session: one job per tenant per hour."""
    since = datetime.now(UTC) - min_interval
    n = 0
    for tid in tenant_ids:
        recent = session.scalar(
            select(Job.id)
            .where(Job.kind == ROLLUP_KIND, Job.tenant_id == tid, Job.created_at >= since)
            .limit(1)
        )
        if recent is None:
            session.add(Job(tenant_id=tid, kind=ROLLUP_KIND, payload={}))
            n += 1
    session.flush()
    return n
