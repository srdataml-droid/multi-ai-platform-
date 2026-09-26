from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, ToolCall
from novaxis_core.metrics import ROLLUP_KIND, enqueue_rollups, rollup_day
from novaxis_core.models import Job, MetricsDaily, Tenant
from novaxis_core.turn import run_turn
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack


@pytest.fixture
def hvac(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        s.expunge(t)
        return t


def test_rollup_counts_and_is_idempotent(hvac: Tenant) -> None:
    v = uuid.uuid4().hex[:10]
    with tenant_session(hvac.id) as s:
        r = ingest(
            s,
            hvac,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref="demo-hvac",
                sender_visitor_id=v,
                body="boiler",
            ),
        )
    fake = FakeLLM(
        script=[
            (
                "ok",
                [
                    ToolCall(
                        "propose_appointment",
                        {
                            "service_code": "repair_visit",
                            "preferred_window": "tomorrow",
                            "notes": "",
                        },
                        "t",
                    )
                ],
            )
        ]
    )
    with tenant_session(hvac.id) as s:
        run_turn(s, hvac, get_pack("hvac"), fake, r.conversation_id)
    today = datetime.now(UTC).date()
    with tenant_session(hvac.id) as s:
        rows = rollup_day(s, hvac, today)
        rows = rollup_day(s, hvac, today)  # second run replaces, never duplicates
        web = next(x for x in rows if x.channel == "webchat")
        assert web.inbound >= 1 and web.answered_under_10s >= 1 and web.bookings_proposed >= 1
        assert (
            s.scalar(
                select(MetricsDaily).where(
                    MetricsDaily.channel == "webchat",
                    MetricsDaily.day == datetime.combine(today, datetime.min.time()),
                )
            )
            is web
        )


def test_enqueue_rollups_once_per_hour(hvac: Tenant) -> None:
    with service_session() as s:
        for j in s.scalars(select(Job).where(Job.kind == ROLLUP_KIND)):
            j.created_at = datetime.now(UTC) - timedelta(hours=2)
    with service_session() as s:
        assert enqueue_rollups(s, [hvac.id]) == 1
        assert enqueue_rollups(s, [hvac.id]) == 0
