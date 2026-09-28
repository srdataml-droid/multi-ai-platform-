"""agent webhooks: push events to a business's own agent instead of making it poll

Each agent key may have a webhook URL; events are signed with a per-key secret that is
stored encrypted (the sensitive-fields key) and shown to the owner once
(docs/agent-api.md). Additive: old code ignores the columns.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_keys", sa.Column("webhook_url", sa.String(length=500)))
    op.add_column("agent_keys", sa.Column("webhook_secret", sa.Text()))


def downgrade() -> None:
    op.drop_column("agent_keys", "webhook_secret")
    op.drop_column("agent_keys", "webhook_url")
