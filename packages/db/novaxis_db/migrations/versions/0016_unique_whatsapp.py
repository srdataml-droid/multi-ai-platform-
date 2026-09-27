"""unique WhatsApp number per business

Inbound WhatsApp messages are routed by the Meta phone-number id in a business's
settings. Like SMS numbers (0013), one id may belong to one business only.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ID = "(settings -> 'channels' -> 'whatsapp' -> 'config' ->> 'phone_number_id')"


def upgrade() -> None:
    op.execute(
        f"CREATE UNIQUE INDEX uq_tenants_whatsapp_number ON tenants (lower({_ID})) "
        f"WHERE coalesce({_ID}, '') <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_whatsapp_number")
