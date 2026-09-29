"""Move everything encrypted over to the newest key (NOVAXIS_SENSITIVE_FIELDS_KEY_NEXT).

Runs inside the deployed app, the one place both keys exist (POST /internal/rekey), in
passes that stop after `budget` rewritten rows so each fits in one serverless request;
call it until `remaining` is 0, then make the new key the only key (docs/encryption.md).
Values already under the newest key are left as they are, so passes can repeat safely.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from novaxis_core.sensitive import is_encrypted, rotate

# (table, column, kind): text columns hold "enc:v1:..."; bytes hold the same as UTF-8;
# JSON columns hold it in values (transcripts in messages.media, answers in extracted).
TARGETS: tuple[tuple[str, str, str], ...] = (
    ("messages", "body", "text"),
    ("conversations", "summary", "text"),
    ("agent_keys", "webhook_secret", "text"),
    ("integrations", "encrypted_credentials", "bytes"),
    ("messages", "media", "json"),
    ("conversations", "extracted", "json"),
)


def _rotate_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _rotate_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rotate_json(v) for v in value]
    return rotate(value) if is_encrypted(value) else value


def rekey(session: Session, budget: int = 2000) -> dict[str, int]:
    """One pass. Returns rows rewritten and rows still under an older key."""
    done = remaining = 0
    for table, column, kind in TARGETS:
        if kind == "bytes":
            where = f"{column} IS NOT NULL"
        elif kind == "json":
            where = f"{column}::text LIKE '%enc:v1:%'"
        else:
            where = f"{column} LIKE 'enc:v1:%'"
        rows = session.execute(text(f"SELECT id, {column} FROM {table} WHERE {where}")).all()
        for row_id, value in rows:
            if kind == "bytes":
                old = bytes(value).decode()
                new: Any = rotate(old)
                changed = new != old
                param: Any = new.encode()
            elif kind == "json":
                data = value if not isinstance(value, str) else json.loads(value)
                new = _rotate_json(data)
                changed = new != data
                param = json.dumps(new)
            else:
                new = rotate(value)
                changed = new != value
                param = new
            if not changed:
                continue
            if done >= budget:
                remaining += 1
                continue
            cast = "CAST(:v AS jsonb)" if kind == "json" else ":v"
            session.execute(
                text(f"UPDATE {table} SET {column} = {cast} WHERE id = :id"),
                {"v": param, "id": row_id},
            )
            done += 1
    session.flush()
    return {"rewritten": done, "remaining": remaining}
