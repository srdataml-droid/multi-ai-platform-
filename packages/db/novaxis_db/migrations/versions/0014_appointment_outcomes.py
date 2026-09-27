"""appointment outcomes: whether the customer turned up

Staff record `attended` or `no_show` after an appointment. These are the labels the
no-show model learns from (docs/ml.md). Additive: old code ignores the columns.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("outcome", sa.String(length=20)))
    op.add_column("appointments", sa.Column("outcome_at", sa.DateTime(timezone=True)))
    op.add_column(
        "appointments",
        sa.Column(
            "outcome_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )
    op.create_check_constraint(
        "ck_appointments_outcome", "appointments", "outcome IN ('attended', 'no_show')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_outcome", "appointments", type_="check")
    op.drop_column("appointments", "outcome_by")
    op.drop_column("appointments", "outcome_at")
    op.drop_column("appointments", "outcome")
