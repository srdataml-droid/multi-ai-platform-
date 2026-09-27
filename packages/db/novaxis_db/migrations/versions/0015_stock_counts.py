"""stock counts: a photo, the network's count, and the count staff confirm

Every confirmed or corrected count is a training label for the stock counter
(docs/ml.md). Tenant table under the usual isolation policy.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"
PREDICATE = "tenant_id = (SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)"


def upgrade() -> None:
    op.create_table(
        "stock_counts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("product", sa.String(length=120), nullable=False),
        sa.Column("photo_key", sa.String(length=300), nullable=True),
        sa.Column("predicted", sa.Integer(), nullable=True),
        sa.Column("raw", sa.Float(), nullable=True),
        sa.Column(
            "points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("synthetic_model", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("confirmed", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("confirmed IS NULL OR confirmed >= 0", name="ck_stock_counts_confirmed"),
    )
    op.create_index("ix_stock_counts_tenant_id", "stock_counts", ["tenant_id", "created_at"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON stock_counts TO {APP_ROLE}")
    op.execute("ALTER TABLE stock_counts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_counts FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON stock_counts FOR ALL TO {APP_ROLE} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON stock_counts")
    op.execute(f"REVOKE ALL PRIVILEGES ON stock_counts FROM {APP_ROLE}")
    op.drop_index("ix_stock_counts_tenant_id", table_name="stock_counts")
    op.drop_table("stock_counts")
