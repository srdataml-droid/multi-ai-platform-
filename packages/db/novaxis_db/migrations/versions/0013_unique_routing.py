"""unique routing addresses: one business per SMS number and per inbound email address

Inbound SMS and email are routed to a business by the number or address in its settings.
Nothing stopped two businesses holding the same one, and routing then picked whichever row
came back first, handing one business's customers to another. These indexes make a second
claim fail. They compare lower-cased values, matching routing.py and the canonical forms
tenant_settings.py stores.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SMS = "(settings -> 'channels' -> 'twilio_sms' -> 'config' ->> 'number')"
_EMAIL = "(settings -> 'channels' -> 'email' -> 'config' ->> 'inbound_address')"


def upgrade() -> None:
    for name, expr in (("uq_tenants_sms_number", _SMS), ("uq_tenants_inbound_email", _EMAIL)):
        op.execute(
            f"CREATE UNIQUE INDEX {name} ON tenants (lower({expr})) "
            f"WHERE coalesce({expr}, '') <> ''"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_inbound_email")
    op.execute("DROP INDEX IF EXISTS uq_tenants_sms_number")
