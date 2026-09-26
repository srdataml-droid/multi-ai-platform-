"""action_proposals: execution outcome columns and edit lineage

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_proposals", sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "action_proposals",
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("action_proposals", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("action_proposals", sa.Column("superseded_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_action_proposals_superseded_by",
        "action_proposals",
        "action_proposals",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_action_proposals_queue", "action_proposals", ["tenant_id", "state", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_action_proposals_queue", table_name="action_proposals")
    op.drop_constraint("fk_action_proposals_superseded_by", "action_proposals", type_="foreignkey")
    op.drop_column("action_proposals", "superseded_by")
    op.drop_column("action_proposals", "error")
    op.drop_column("action_proposals", "result")
    op.drop_column("action_proposals", "executed_at")
