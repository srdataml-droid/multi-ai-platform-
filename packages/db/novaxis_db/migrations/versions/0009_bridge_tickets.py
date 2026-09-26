"""bridge_tickets: booking changes handed to a vendor tool with no API (Chunk 11)

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"
PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "bridge_tickets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("ref", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entered_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("action IN ('create','update','cancel')", name="ck_bridge_action"),
        sa.CheckConstraint(
            "status IN ('queued','emailed','not_emailed','entered')", name="ck_bridge_status"
        ),
        sa.UniqueConstraint("tenant_id", "ref", "action", "starts_at", name="uq_bridge_ticket"),
    )
    op.create_index("ix_bridge_tickets_tenant_id", "bridge_tickets", ["tenant_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON bridge_tickets TO {APP_ROLE}")
    op.execute("ALTER TABLE bridge_tickets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bridge_tickets FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON bridge_tickets FOR ALL TO {APP_ROLE} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON bridge_tickets")
    op.execute(f"REVOKE ALL PRIVILEGES ON bridge_tickets FROM {APP_ROLE}")
    op.drop_index("ix_bridge_tickets_tenant_id", table_name="bridge_tickets")
    op.drop_table("bridge_tickets")
