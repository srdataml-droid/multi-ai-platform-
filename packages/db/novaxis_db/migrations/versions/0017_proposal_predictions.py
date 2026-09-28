"""proposal predictions: what the approval model expected, stored when it was asked

When a proposal waits for staff, the approval model's prediction (probability staff
approve it as written, and why) is stored with it. Stored, not recomputed, so the shadow
report compares staff decisions with what the model said *before* it knew them
(docs/ml.md). Additive: old code ignores the column.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("action_proposals", sa.Column("prediction", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("action_proposals", "prediction")
