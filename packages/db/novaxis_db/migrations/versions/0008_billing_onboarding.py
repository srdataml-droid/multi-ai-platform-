"""billing and onboarding: trial window, onboarding marker, billing refs, provider event log

`billing_events` records every billing webhook by the provider's event id, so a replayed
delivery is a no-op. It is service-only: the app role has no privileges on it, and RLS is
forced with no policy, so even a mistaken grant would expose nothing.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("trial_ends_at", sa.DateTime(timezone=True)))
    op.add_column("tenants", sa.Column("onboarded_at", sa.DateTime(timezone=True)))
    op.add_column("tenants", sa.Column("billing_customer_ref", sa.String(length=200)))
    op.add_column("tenants", sa.Column("billing_subscription_ref", sa.String(length=200)))
    op.create_unique_constraint(
        "uq_tenants_billing_customer_ref", "tenants", ["billing_customer_ref"]
    )

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=200), primary_key=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="RESTRICT")),
        sa.Column("outcome", sa.String(length=200), nullable=False),
        sa.Column("payload", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute("ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_events FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_constraint("uq_tenants_billing_customer_ref", "tenants", type_="unique")
    op.drop_column("tenants", "billing_subscription_ref")
    op.drop_column("tenants", "billing_customer_ref")
    op.drop_column("tenants", "onboarded_at")
    op.drop_column("tenants", "trial_ends_at")
