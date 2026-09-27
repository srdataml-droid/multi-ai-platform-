"""Export confirmed stock counts as a training folder (photos + labels.jsonl).

    uv run python -m novaxis_ml.stock.export --out /path/to/photos [--tenant <uuid>]

Only counts a person confirmed or corrected are exported; the network's own guesses are
never used as labels. Photos come from the platform's file store, so they must be in
durable storage (Supabase, see fault E2), not the API's temporary disk.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from novaxis_core.models import StockCountRow
from novaxis_core.storage import get_store
from novaxis_db.session import service_session


def export(out: Path, tenant_id: uuid.UUID | None = None) -> tuple[int, int]:
    """Returns (photos written, photos missing from storage)."""
    out.mkdir(parents=True, exist_ok=True)
    store = get_store()
    lines: list[str] = []
    missing = 0
    with service_session() as s:
        stmt = select(StockCountRow).where(
            StockCountRow.confirmed.is_not(None), StockCountRow.photo_key.is_not(None)
        )
        if tenant_id is not None:
            stmt = stmt.where(StockCountRow.tenant_id == tenant_id)
        for row in s.scalars(stmt.order_by(StockCountRow.created_at)):
            assert row.photo_key is not None
            try:
                data, _ = store.get(row.photo_key)
            except (FileNotFoundError, ValueError):
                missing += 1
                continue
            name = f"{row.id}{Path(row.photo_key).suffix}"
            (out / name).write_bytes(data)
            lines.append(
                json.dumps({"image": name, "count": row.confirmed, "product": row.product})
            )
    (out / "labels.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))
    return len(lines), missing


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="novaxis_ml.stock.export")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tenant", default=None)
    a = ap.parse_args()
    n, missing = export(Path(a.out), uuid.UUID(a.tenant) if a.tenant else None)
    print(f"exported {n} confirmed photos to {a.out}; {missing} photos no longer in storage")
    sys.exit(0)
