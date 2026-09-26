"""Serve stored media to staff. Only the local store needs this; Supabase hands
out signed URLs. The key starts with the tenant id, and the tenant-scoped
session proves the caller belongs to that tenant."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from novaxis_api.auth import CurrentPrincipal
from novaxis_core.sensitive import READ_ROLES
from novaxis_core.storage import get_store

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{key:path}")
def get_media(key: str, principal: CurrentPrincipal) -> Response:
    if principal.role not in READ_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "viewers cannot open attachments")
    parts = key.split("/")
    # The prefix check alone is not enough: "<mine>/../<theirs>/photo.jpg" starts with our
    # tenant id and resolves into another tenant's folder.
    if parts[0] != str(principal.tenant_id) or any(x in ("", ".", "..") for x in parts):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such object")
    try:
        data, content_type = get_store().get(key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such object") from exc
    return Response(
        content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"}
    )
