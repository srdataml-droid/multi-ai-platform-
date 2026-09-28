"""agent keys: let a business's own agent (e.g. one built with Hermes) use the agent API

Only a SHA-256 hash of each key is stored; the key is shown once when created. A key
belongs to one business, works only on /agent/v1, can be revoked, and records when it
was last used (docs/agent-api.md). Tenant table under the usual isolation policy.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"
PREDICATE = "tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)"


def upgrade() -> None:
    op.create_table(
        "agent_keys",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_agent_keys_hash", "agent_keys", ["key_hash"], unique=True)
    op.create_index("ix_agent_keys_tenant_id", "agent_keys", ["tenant_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON agent_keys TO {APP_ROLE}")
    op.execute("ALTER TABLE agent_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON agent_keys FOR ALL TO {APP_ROLE} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON agent_keys")
    op.execute(f"REVOKE ALL PRIVILEGES ON agent_keys FROM {APP_ROLE}")
    op.drop_index("ix_agent_keys_tenant_id", table_name="agent_keys")
    op.drop_index("uq_agent_keys_hash", table_name="agent_keys")
    op.drop_table("agent_keys")
