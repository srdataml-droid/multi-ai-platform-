"""Access requests, erasure and the retention purge: everything for one customer, nothing
for anyone else, and only past the business's retention period."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.models import (
    ActionProposal,
    Appointment,
    AuditLog,
    BridgeTicket,
    Contact,
    Conversation,
    Job,
    Message,
    Tenant,
)
from novaxis_core.privacy import enqueue_purges, erase_contact, export_contact, purge_expired
from novaxis_core.settings import get_settings
from novaxis_core.storage import get_store
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session


@pytest.fixture
def store_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("NOVAXIS_STORAGE_LOCAL_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_store.cache_clear()
    yield tmp_path
    get_store.cache_clear()


@pytest.fixture
def tenants(migrated: str) -> tuple[Tenant, Tenant]:
    with service_session(migrated) as s:
        seed(s)
        out = []
        for slug in ("demo-hvac", "demo-dental"):
            t = s.scalar(select(Tenant).where(Tenant.slug == slug))
            assert t is not None
            s.expunge(t)
            out.append(t)
    return out[0], out[1]


def _customer(t: Tenant, text: str, with_file: bool = False) -> tuple[uuid.UUID, uuid.UUID]:
    """A web-chat customer with one message, a booking, a proposal, a queued job, a bridge
    hand-off and (optionally) a stored photo. Returns (contact_id, conversation_id)."""
    v = uuid.uuid4().hex[:10]
    with tenant_session(t.id) as s:
        r = ingest(
            s,
            t,
            NormalisedInbound(
                channel="webchat",
                provider_ref=f"webchat:{v}:{uuid.uuid4().hex[:6]}",
                tenant_ref=t.slug,
                sender_visitor_id=v,
                sender_name=text,
                body=text,
            ),
        )
        media = []
        if with_file:
            mid = uuid.uuid4()
            key = f"{t.id}/{mid}/0.jpg"
            get_store().put(key, b"photo", "image/jpeg")
            media = [{"key": key, "content_type": "image/jpeg"}]
            s.add(
                Message(
                    id=mid,
                    tenant_id=t.id,
                    conversation_id=r.conversation_id,
                    direction="inbound",
                    channel="webchat",
                    author="customer",
                    body=f"photo of {text}",
                    media=media,
                )
            )
        p = ActionProposal(
            tenant_id=t.id,
            conversation_id=r.conversation_id,
            kind="propose_appointment",
            params={"notes": text},
            risk="low",
            state="executed",
        )
        s.add(p)
        s.flush()
        start = datetime.now(UTC) - timedelta(days=3)
        a = Appointment(
            tenant_id=t.id,
            contact_id=r.contact_id,
            conversation_id=r.conversation_id,
            proposal_id=p.id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_code="repair_visit",
            status="confirmed",
        )
        s.add(a)
        s.flush()
        s.add(
            BridgeTicket(
                tenant_id=t.id,
                ref=uuid.uuid4().hex[:8],
                action="create",
                starts_at=a.starts_at,
                ends_at=a.ends_at,
                summary=text,
                details={"appointment_id": str(a.id), "customer_name": text},
            )
        )
        return r.contact_id, r.conversation_id


def _count(model: type, **where: object) -> int:
    with service_session() as s:
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return int(s.scalar(stmt) or 0)


def test_export_holds_everything_for_one_customer_and_nothing_for_another(
    tenants: tuple[Tenant, Tenant], store_dir: Path
) -> None:
    hvac, _ = tenants
    mine, _ = _customer(hvac, "Alice Export", with_file=True)
    _customer(hvac, "Bob Other")
    with tenant_session(hvac.id) as s:
        c = s.get(Contact, mine)
        assert c is not None
        data = export_contact(s, c, frozenset())
    text = str(data)
    assert data["contact"]["name"] == "Alice Export"
    assert "photo of Alice Export" in text and "/0.jpg" in text
    assert data["appointments"] and data["conversations"][0]["messages"]
    assert "Bob Other" not in text


def test_erasure_removes_one_customer_everywhere_and_touches_no_one_else(
    tenants: tuple[Tenant, Tenant], store_dir: Path
) -> None:
    hvac, dental = tenants
    gone, gone_conv = _customer(hvac, "Carol Erase", with_file=True)
    kept, kept_conv = _customer(hvac, "Dan Keep", with_file=True)
    other, _ = _customer(dental, "Eve Dental")
    with tenant_session(hvac.id) as s:
        s.add(
            Job(tenant_id=hvac.id, kind="worker_turn", payload={"conversation_id": str(gone_conv)})
        )
        s.add(
            Job(tenant_id=hvac.id, kind="worker_turn", payload={"conversation_id": str(kept_conv)})
        )
    files_before = sorted(p.name for p in store_dir.rglob("*.jpg"))
    assert len(files_before) == 2
    with service_session() as s:
        counts = erase_contact(s, hvac.id, gone, "test", "erasure request")
    assert counts["conversations"] == 1 and counts["files"] == 1 and counts["appointments"] == 1
    assert counts["jobs"] >= 1 and counts["bridge_tickets"] == 1
    assert _count(Contact, id=gone) == 0
    assert _count(Conversation, contact_id=gone) == 0
    assert _count(Message, conversation_id=gone_conv) == 0
    assert _count(Appointment, contact_id=gone) == 0
    assert _count(ActionProposal, conversation_id=gone_conv) == 0
    with service_session() as s:
        assert not list(
            s.scalars(select(BridgeTicket).where(BridgeTicket.summary == "Carol Erase"))
        )
        assert not list(
            s.scalars(select(Job).where(Job.payload["conversation_id"].astext == str(gone_conv)))
        )
        audit = s.scalar(
            select(AuditLog).where(AuditLog.event == "contact.erased", AuditLog.subject_id == gone)
        )
        assert audit is not None and "Carol" not in str(audit.diff)
    assert len(list(store_dir.rglob("*.jpg"))) == 1, "only the erased customer's photo went"
    # Everyone else is untouched, in this business and the other one.
    assert _count(Contact, id=kept) == 1 and _count(Message, conversation_id=kept_conv) >= 1
    assert _count(Appointment, contact_id=kept) == 1
    assert _count(Contact, id=other) == 1
    with service_session() as s, pytest.raises(LookupError):
        erase_contact(s, dental.id, kept, "test", "wrong business")


def test_purge_takes_only_customers_past_retention_and_only_in_that_business(
    tenants: tuple[Tenant, Tenant], store_dir: Path
) -> None:
    hvac, dental = tenants
    old, old_conv = _customer(hvac, "Old Customer")
    booked, booked_conv = _customer(hvac, "Old But Booked")
    fresh, _ = _customer(hvac, "Fresh Customer")
    other_old, other_conv = _customer(dental, "Old Dental")
    long_ago = datetime.now(UTC) - timedelta(days=800)
    with service_session() as s:
        for cid, conv in ((old, old_conv), (booked, booked_conv), (other_old, other_conv)):
            s.execute(update(Contact).where(Contact.id == cid).values(created_at=long_ago))
            s.execute(
                update(Conversation).where(Conversation.id == conv).values(created_at=long_ago)
            )
            s.execute(
                update(Message).where(Message.conversation_id == conv).values(created_at=long_ago)
            )
            s.execute(
                update(Appointment)
                .where(Appointment.contact_id == cid)
                .values(
                    created_at=long_ago,
                    starts_at=long_ago,
                    ends_at=long_ago + timedelta(hours=1),
                )
            )
        # A booking still to come keeps a customer, however old the conversation.
        s.execute(
            update(Appointment)
            .where(Appointment.contact_id == booked)
            .values(
                starts_at=datetime.now(UTC) + timedelta(days=5),
                ends_at=datetime.now(UTC) + timedelta(days=5, hours=1),
            )
        )
        t = s.get(Tenant, hvac.id)
        assert t is not None
        n = purge_expired(s, t)
    assert n >= 1
    assert _count(Contact, id=old) == 0
    assert _count(Contact, id=booked) == 1
    assert _count(Contact, id=fresh) == 1
    assert _count(Contact, id=other_old) == 1, "another business's purge is its own"
    with service_session() as s:
        t = s.get(Tenant, hvac.id)
        assert t is not None
        t.settings = {**t.settings, "retention_days": 3650}
        s.flush()
        assert purge_expired(s, t) == 0, "a longer retention keeps them"
        t.settings = {k: v for k, v in t.settings.items() if k != "retention_days"}


def test_the_purge_is_queued_once_a_day_per_business(tenants: tuple[Tenant, Tenant]) -> None:
    hvac, dental = tenants
    with service_session() as s:
        s.execute(update(Job).where(Job.kind == "retention_purge").values(state="done"))
        first = enqueue_purges(s, [hvac.id, dental.id])
        again = enqueue_purges(s, [hvac.id, dental.id])
    assert again == 0 and first <= 2
