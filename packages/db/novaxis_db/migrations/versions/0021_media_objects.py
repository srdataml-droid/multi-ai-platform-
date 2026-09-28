"""media_objects: customer photos and voice notes kept in Postgres

On Vercel the disk is temporary, so the local store loses files when a function
restarts. The `db` storage backend keeps them here instead, with no extra keys.

Service-only like `rate_limits` (0012): forced RLS, no policy, no grant. Only the
service connection (the storage code) reads and writes it; the app role and Supabase's
public API see nothing. Access control stays in the API (routes_media).

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE media_objects ("
        " key text PRIMARY KEY,"
        " content_type text NOT NULL,"
        " data bytea NOT NULL,"
        " created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute("ALTER TABLE media_objects ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE media_objects FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS media_objects")
