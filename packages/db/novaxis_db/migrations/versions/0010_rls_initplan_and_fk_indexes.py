"""tenancy policies evaluated once per query; indexes on the hot foreign keys

The isolation predicate called current_setting() for every row it checked. Wrapped in a
scalar subquery, Postgres evaluates it once per statement (an "initplan"), which is what
Supabase's performance advisor asks for. The rule itself is unchanged.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
# Every table with a tenant_id policy as of this revision (plus tenants, keyed on id).
TABLES = (
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
)
INDEXES = (
    ("ix_conversations_contact", "conversations", "contact_id"),
    ("ix_appointments_contact", "appointments", "contact_id"),
    ("ix_approvals_proposal", "approvals", "proposal_id"),
    ("ix_action_proposals_conversation", "action_proposals", "conversation_id"),
    ("ix_billing_events_tenant", "billing_events", "tenant_id"),
)


def _policy(table: str, column: str, predicate: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} FOR ALL TO {APP_ROLE} "
        f"USING ({column} = {predicate}) WITH CHECK ({column} = {predicate})"
    )


def upgrade() -> None:
    fast = f"(SELECT {SETTING})"
    _policy("tenants", "id", fast)
    for table in TABLES:
        _policy(table, "tenant_id", fast)
    for name, table, column in INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table)
    _policy("tenants", "id", SETTING)
    for table in TABLES:
        _policy(table, "tenant_id", SETTING)
