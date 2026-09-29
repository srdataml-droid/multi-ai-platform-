"""encrypt message text, voice-note transcripts and conversation summaries

What customers write (and the assistant's replies, which repeat it) can hold health or
money details. From this revision the application encrypts `messages.body` and
`conversations.summary` on every write (sensitive.EncryptedText) and voice-note
transcripts inside `messages.media`; this migration encrypts what was stored before.

Uses the same key as the sensitive fields (NOVAXIS_SENSITIVE_FIELDS_KEY), so it must run
where the application runs (auto-migrate on deploy does). Idempotent: encrypted values
are left alone. Downgrade decrypts.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from novaxis_core.sensitive import PREFIX, decrypt, encrypt

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BATCH = 500


def _column(table: str, column: str, change: Callable[[str], str], todo: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL AND {todo}"),
        {"p": PREFIX + "%"},
    ).all()
    for i in range(0, len(rows), BATCH):
        bind.execute(
            sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
            [{"id": r[0], "v": change(r[1])} for r in rows[i : i + BATCH]],
        )


def _transcripts(change: Callable[[str], str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, media FROM messages WHERE media::text LIKE '%\"transcript\":%'")
    ).all()
    updates: list[dict[str, Any]] = []
    for msg_id, media in rows:
        entries = media if isinstance(media, list) else json.loads(media)
        new = [
            {**e, "transcript": change(e["transcript"])} if e.get("transcript") else e
            for e in entries
        ]
        if new != entries:
            updates.append({"id": msg_id, "m": json.dumps(new)})
    for i in range(0, len(updates), BATCH):
        bind.execute(
            sa.text("UPDATE messages SET media = CAST(:m AS jsonb) WHERE id = :id"),
            updates[i : i + BATCH],
        )


def upgrade() -> None:
    plain = "{col} NOT LIKE :p"
    _column("messages", "body", encrypt, plain.format(col="body"))
    _column("conversations", "summary", encrypt, plain.format(col="summary"))
    _transcripts(encrypt)


def downgrade() -> None:
    enc = "{col} LIKE :p"
    _column("messages", "body", decrypt, enc.format(col="body"))
    _column("conversations", "summary", decrypt, enc.format(col="summary"))
    _transcripts(decrypt)
