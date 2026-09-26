"""channels: visitor ids, message media, idempotency index, delivery-column grant

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "novaxis_app"


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column(
            "visitor_ids",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "media",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # One inbound provider message id lands once per tenant and channel, so webhook
    # replays are no-ops. Outbound refs are informational and not constrained.
    op.create_index(
        "ux_messages_inbound_provider_ref",
        "messages",
        ["tenant_id", "channel", "provider_ref"],
        unique=True,
        postgresql_where=sa.text("provider_ref IS NOT NULL AND direction = 'inbound'"),
    )
    # Contact lookups by phone, email and visitor id.
    op.execute("CREATE INDEX ix_contacts_phones ON contacts USING gin (phones)")
    op.execute("CREATE INDEX ix_contacts_emails ON contacts USING gin (emails)")
    op.execute("CREATE INDEX ix_contacts_visitor_ids ON contacts USING gin (visitor_ids)")
    op.create_index(
        "ix_conversations_thread", "conversations", ["tenant_id", "contact_id", "channel", "status"]
    )
    # Tenant routing by channel identifier lives inside settings JSONB.
    op.execute(
        "CREATE INDEX ix_tenants_settings_channels ON tenants USING gin ((settings->'channels'))"
    )
    # messages stay append-only except for the two delivery columns an outbound send fills in.
    op.execute(f"GRANT UPDATE (provider_ref, delivered_at) ON messages TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (provider_ref, delivered_at) ON messages FROM {APP_ROLE}")
    op.execute("DROP INDEX IF EXISTS ix_tenants_settings_channels")
    op.drop_index("ix_conversations_thread", table_name="conversations")
    op.execute("DROP INDEX IF EXISTS ix_contacts_visitor_ids")
    op.execute("DROP INDEX IF EXISTS ix_contacts_emails")
    op.execute("DROP INDEX IF EXISTS ix_contacts_phones")
    op.drop_index("ux_messages_inbound_provider_ref", table_name="messages")
    op.drop_column("messages", "media")
    op.drop_column("contacts", "visitor_ids")
