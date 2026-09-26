"""hosted Postgres hardening: keep Supabase's public API roles away from these tables

On Supabase, tables in `public` are exposed through its REST API to the roles `anon`
and `authenticated`. This platform never uses that API; its only door is the app. So
those roles get no privileges on any table, now or in future migrations. On plain
Postgres the roles do not exist and this migration does nothing.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
              EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
              EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r
              );
            END IF;
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    # Deliberately no re-grant: exposing these tables was never intended.
    pass
