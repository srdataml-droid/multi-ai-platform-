"""messages: allow the app role to fill in media once fetched

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"


def upgrade() -> None:
    # messages stays append-only; media is enriched after the fact by the fetch job.
    op.execute(f"GRANT UPDATE (media) ON messages TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (media) ON messages FROM {APP_ROLE}")
