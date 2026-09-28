"""unique WhatsApp-through-Twilio number per business

WhatsApp messages arriving through Twilio are routed by the business's WhatsApp number
(or its SMS number when it has none). Like SMS numbers (0013), one number may belong to
one business only.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NUMBER = "(settings -> 'channels' -> 'twilio_whatsapp' -> 'config' ->> 'number')"


def upgrade() -> None:
    op.execute(
        f"CREATE UNIQUE INDEX uq_tenants_twilio_whatsapp_number ON tenants (lower({_NUMBER})) "
        f"WHERE coalesce({_NUMBER}, '') <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_twilio_whatsapp_number")
