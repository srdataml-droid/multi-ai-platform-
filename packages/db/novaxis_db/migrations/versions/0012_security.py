"""security: per-account login codes for demo mode; a shared rate-limit counter

`rate_limits` is service-only like `billing_events`: forced RLS, no policy, no grant. It
holds a counter per key per fixed window, so every serverless instance sees the same count.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("login_code_hash", sa.String(length=200)))
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("key", "window_start"),
    )
    op.execute("ALTER TABLE rate_limits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rate_limits FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("rate_limits")
    op.drop_column("users", "login_code_hash")
