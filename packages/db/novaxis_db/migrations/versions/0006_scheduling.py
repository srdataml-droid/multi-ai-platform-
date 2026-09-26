"""appointments: link to the conversation and the proposal that offered the slot

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("conversation_id", sa.UUID(), nullable=True))
    op.add_column("appointments", sa.Column("proposal_id", sa.UUID(), nullable=True))
    op.add_column("appointments", sa.Column("notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_conversation",
        "appointments",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_proposal",
        "appointments",
        "action_proposals",
        ["proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_appointments_window", "appointments", ["tenant_id", "status", "starts_at"])
    op.create_index("ix_appointments_conversation", "appointments", ["conversation_id"])
    op.create_index("ix_appointments_proposal", "appointments", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_proposal", table_name="appointments")
    op.drop_index("ix_appointments_conversation", table_name="appointments")
    op.drop_index("ix_appointments_window", table_name="appointments")
    op.drop_constraint("fk_appointments_proposal", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointments_conversation", "appointments", type_="foreignkey")
    op.drop_column("appointments", "notes")
    op.drop_column("appointments", "proposal_id")
    op.drop_column("appointments", "conversation_id")
