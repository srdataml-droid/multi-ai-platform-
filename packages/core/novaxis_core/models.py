"""The core tables, as SQLAlchemy models.

Why here and not in the db package: apps and packs talk about these rows, and
they must not import migrations to do so. The db package owns how the tables
are created and secured (migrations, RLS); this module owns what they mean.

Every table carries `tenant_id`. Row Level Security in Postgres filters on it,
so a query issued inside `tenant_session(t)` can only ever see tenant t's rows.
See docs/ARCHITECTURE.md section 3 and ADR 0003.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Allowed values live here as tuples so migrations, models and tests agree.
TENANT_STATUSES = ("active", "paused", "trial", "closed")
USER_ROLES = ("owner", "staff", "viewer", "operator")
CONVERSATION_STATUSES = ("open", "waiting_human", "waiting_customer", "closed")
MESSAGE_DIRECTIONS = ("inbound", "outbound")
MESSAGE_AUTHORS = ("customer", "worker", "human", "system")
JOB_STATES = ("queued", "running", "done", "failed")
RISK_LEVELS = ("low", "medium", "high")
PROPOSAL_STATES = (
    "proposed",
    "auto_approved",
    "awaiting",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
)
APPROVAL_DECISIONS = ("approve", "reject", "edit")
BRIDGE_ACTIONS = ("create", "update", "cancel")
BRIDGE_STATUSES = ("queued", "emailed", "not_emailed", "entered")
APPOINTMENT_STATUSES = ("proposed", "held", "confirmed", "cancelled", "completed", "no_show")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


def _tenant_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class Base(DeclarativeBase):
    """Declarative base for every core table."""


class Tenant(Base):
    """One business. Multi-location businesses are one tenant with many locations."""

    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    pack_id: Mapped[str] = mapped_column(String(40), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    plan: Mapped[str] = mapped_column(String(40), nullable=False, server_default="trial")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="trial")
    worker_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    data_region: Mapped[str] = mapped_column(String(10), nullable=False, server_default="uk")
    # Billing and onboarding (Chunk 10). Trial ends by date or by message cap, whichever first.
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_customer_ref: Mapped[str | None] = mapped_column(String(200), unique=True)
    billing_subscription_ref: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="Europe/London"
    )
    calendar_ref: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    """A dashboard login. `auth_subject` is the identity provider's stable id (JWT sub)."""

    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    auth_subject: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    # Demo mode only: a personal login code (scrypt hash) given once at sign-up.
    login_code_hash: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()


class Contact(Base):
    """A person the business talks to. `pack_fields` holds vertical-specific, possibly
    sensitive, data and is excluded from logs and analytics."""

    __tablename__ = "contacts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    display_name: Mapped[str | None] = mapped_column(String(200))
    phones: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, server_default=text("'{}'")
    )
    emails: Mapped[list[str]] = mapped_column(
        ARRAY(String(320)), nullable=False, server_default=text("'{}'")
    )
    visitor_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, server_default=text("'{}'")
    )
    consent: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    pack_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    summary: Mapped[str | None] = mapped_column(Text)
    extracted: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    takeover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class Message(Base):
    """Append-only. The app role has no UPDATE or DELETE on this table."""

    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    author: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(200))
    media: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Job(Base):
    """The queue. Picked with SELECT ... FOR UPDATE SKIP LOCKED (Chunk 3)."""

    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    locked_by: Mapped[str | None] = mapped_column(String(120))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class ActionProposal(Base):
    __tablename__ = "action_proposals"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    risk: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="proposed")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service_code: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="proposed")
    external_ref: Mapped[str | None] = mapped_column(String(200))
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    customer_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    """Append-only trail of who did what. Written by application code (ADR 0004)."""

    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_table: Mapped[str | None] = mapped_column(String(60))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    diff: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()


class Integration(Base):
    """A connected external system. Credentials are encrypted before they reach this row."""

    __tablename__ = "integrations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    health: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    created_at: Mapped[datetime] = _created_at()


class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    day: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    inbound: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    answered_under_10s: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    intake_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bookings_proposed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bookings_approved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    escalations: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    human_takeovers: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class UsageEvent(Base):
    """Metered usage per tenant: tokens, messages, minutes. Pricing reads this (Chunk 10)."""

    __tablename__ = "usage_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()


class PushSubscription(Base):
    """One browser or phone that asked for staff alerts (Web Push). Free, no provider
    account: the only alert channel that works before email or SMS is connected."""

    __tablename__ = "push_subscriptions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class BridgeTicket(Base):
    """One booking change handed to a vendor tool that has no API (Chunk 11). The office
    enters it by hand and marks it entered; the reference ties the vendor's next diary
    export back to our appointment."""

    __tablename__ = "bridge_tickets"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    ref: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class RateLimit(Base):
    """Requests counted per key per fixed window. Service-only."""

    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class BillingEvent(Base):
    """One billing webhook delivery, keyed by the provider's event id. Service-only: the app
    role has no privileges on it. A replayed delivery finds its row and does nothing."""

    __tablename__ = "billing_events"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT")
    )
    outcome: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    received_at: Mapped[datetime] = _created_at()


# Tables that carry tenant_id and therefore get an RLS policy. The migration and
# the RLS test both iterate this list, so a new table cannot be forgotten.
TENANT_TABLES: tuple[str, ...] = (
    "locations",
    "users",
    "contacts",
    "conversations",
    "messages",
    "jobs",
    "action_proposals",
    "approvals",
    "appointments",
    "audit_log",
    "integrations",
    "metrics_daily",
    "usage_events",
    "bridge_tickets",
    "push_subscriptions",
)

APPEND_ONLY_TABLES: tuple[str, ...] = ("messages", "audit_log")

# Tables the app role may not touch at all: RLS forced, no policy, no grant. Only the
# service session (webhooks, operator tooling) reads and writes them.
SERVICE_ONLY_TABLES: tuple[str, ...] = ("billing_events", "rate_limits")
