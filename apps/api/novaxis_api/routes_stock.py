"""Stock counting from a photo: staff snap a shelf, the network counts, staff confirm or
correct. Every confirmed count is a training label for the next version of the counter
(docs/ml.md)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from novaxis_api.auth import CurrentPrincipal, TenantDb
from novaxis_core.models import AuditLog, StockCountRow, Tenant
from novaxis_core.stock_count import counter_for
from novaxis_core.storage import MediaRejectedError, check_media, get_store

router = APIRouter(prefix="/stock", tags=["stock"])
STAFF = {"owner", "staff", "operator"}


def _out(r: StockCountRow) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "product": r.product,
        "predicted": r.predicted,
        "points": r.points,
        "confirmed": r.confirmed,
        "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        "synthetic_model": r.synthetic_model,
        "photo_url": get_store().url_for(r.photo_key) if r.photo_key else None,
        "created_at": r.created_at.isoformat(),
    }


@router.post("/counts")
async def count_photo(
    principal: CurrentPrincipal,
    session: TenantDb,
    product: Annotated[str, Form(min_length=1, max_length=120)],
    photo: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    if principal.role not in STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    data = await photo.read()
    content_type = photo.content_type or "application/octet-stream"
    try:
        check_media(data, content_type)
        if not content_type.startswith("image/"):
            raise MediaRejectedError("only photos can be counted")
    except MediaRejectedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    tenant = session.scalar(select(Tenant))
    assert tenant is not None
    row = StockCountRow(
        tenant_id=tenant.id, product=product.strip(), created_by=principal.user_id, points=[]
    )
    session.add(row)
    session.flush()
    counter = counter_for(tenant.slug)
    if counter is not None:
        try:
            result = counter.count(data)
        except Exception as exc:  # noqa: BLE001 - an unreadable photo is the caller's error
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "that file could not be read as a photo"
            ) from exc
        row.predicted, row.raw = result.count, result.raw
        row.points = [list(p) for p in result.points]
        row.model, row.synthetic_model = result.model[:60], result.synthetic
    ext = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
    key = f"{tenant.id}/stock-{row.id}/0.{ext}"
    get_store().put(key, data, content_type)
    row.photo_key = key
    session.flush()
    return _out(row)


@router.get("/counts")
def list_counts(principal: CurrentPrincipal, session: TenantDb, limit: int = 50) -> dict[str, Any]:
    rows = session.scalars(
        select(StockCountRow)
        .order_by(StockCountRow.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return {"items": [_out(r) for r in rows]}


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(ge=0, le=100_000)


@router.post("/counts/{count_id}/confirm")
def confirm(
    count_id: uuid.UUID, body: ConfirmIn, principal: CurrentPrincipal, session: TenantDb
) -> dict[str, Any]:
    """Staff say the true count: the network's number, or their correction."""
    if principal.role not in STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    row = session.get(StockCountRow, count_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stock count not found")
    row.confirmed = body.count
    row.confirmed_at = datetime.now(UTC)
    row.confirmed_by = principal.user_id
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=f"user:{principal.user_id}",
            event="stock.confirmed",
            subject_table="stock_counts",
            subject_id=row.id,
            diff={"predicted": row.predicted, "confirmed": body.count},
        )
    )
    session.flush()
    return _out(row)
