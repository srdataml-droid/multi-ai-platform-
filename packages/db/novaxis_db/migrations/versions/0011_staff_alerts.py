"""staff alerts: browser push subscriptions; proposals can expire; customers confirm by text

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"
PREDICATE = "tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
OLD_STATES = "'proposed','auto_approved','awaiting','approved','rejected','executed','failed'"


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index("ix_push_subscriptions_tenant_id", "push_subscriptions", ["tenant_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO {APP_ROLE}")
    op.execute("ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE push_subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON push_subscriptions FOR ALL TO {APP_ROLE} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.drop_constraint("ck_action_proposals_state", "action_proposals", type_="check")
    op.create_check_constraint(
        "ck_action_proposals_state", "action_proposals", f"state IN ({OLD_STATES},'expired')"
    )
    op.add_column("appointments", sa.Column("customer_confirmed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("appointments", "customer_confirmed_at")
    op.execute("UPDATE action_proposals SET state = 'rejected' WHERE state = 'expired'")
    op.drop_constraint("ck_action_proposals_state", "action_proposals", type_="check")
    op.create_check_constraint(
        "ck_action_proposals_state", "action_proposals", f"state IN ({OLD_STATES})"
    )
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON push_subscriptions")
    op.execute(f"REVOKE ALL PRIVILEGES ON push_subscriptions FROM {APP_ROLE}")
    op.drop_index("ix_push_subscriptions_tenant_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
