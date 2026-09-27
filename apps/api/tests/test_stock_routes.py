"""Stock counting through the API: photo in, count and item positions out, staff confirm or
correct, and confirmed counts export as training data."""

from __future__ import annotations

import io
import json
import random
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_core.models import Tenant, User
from novaxis_core.settings import get_settings
from novaxis_core.storage import get_store
from novaxis_db.seed import seed
from novaxis_db.session import service_session
from novaxis_ml.stock.synthetic import shelf_photo

OWNER = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
DENTAL = {"Authorization": f"Bearer {mint('dev|owner@demo-dental')}"}


@pytest.fixture
def client(migrated: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NOVAXIS_STORAGE_LOCAL_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    get_store.cache_clear()
    with service_session(migrated) as s:
        seed(s)
    yield TestClient(create_app())
    get_store.cache_clear()


def _photo(seed: int = 2024) -> tuple[bytes, int]:
    img, pts = shelf_photo(random.Random(seed))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue(), len(pts)


def _count(c: TestClient, headers: dict[str, str], data: bytes, ctype: str = "image/jpeg"):  # type: ignore[no-untyped-def]
    return c.post(
        "/stock/counts",
        headers=headers,
        data={"product": "Cola 330ml"},
        files={"photo": ("shelf.jpg", data, ctype)},
    )


def test_a_photo_is_counted_shown_corrected_and_exported_as_a_label(
    client: TestClient, tmp_path: Path
) -> None:
    data, truth = _photo()
    r = _count(client, OWNER, data)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["predicted"] is not None and abs(row["predicted"] - truth) <= 3
    assert row["synthetic_model"] is True, "the demo model says it is a demo"
    assert len(row["points"]) >= truth // 2, "dots show what was counted"
    assert client.get(row["photo_url"], headers=OWNER).content == data

    fixed = client.post(f"/stock/counts/{row['id']}/confirm", json={"count": truth}, headers=OWNER)
    assert fixed.status_code == 200 and fixed.json()["confirmed"] == truth
    listed = client.get("/stock/counts", headers=OWNER).json()["items"]
    assert listed[0]["id"] == row["id"] and listed[0]["confirmed"] == truth

    # Another business cannot see or confirm it.
    assert (
        client.post(
            f"/stock/counts/{row['id']}/confirm", json={"count": 1}, headers=DENTAL
        ).status_code
        == 404
    )
    assert all(
        i["id"] != row["id"] for i in client.get("/stock/counts", headers=DENTAL).json()["items"]
    )

    from novaxis_ml.stock.export import export

    with service_session() as s:
        tid = s.scalar(select(Tenant.id).where(Tenant.slug == "demo-hvac"))
    n, missing = export(tmp_path / "train", tid)
    labels = [
        json.loads(line) for line in (tmp_path / "train" / "labels.jsonl").read_text().splitlines()
    ]
    mine = [x for x in labels if x["image"].startswith(row["id"])]
    assert n >= 1 and missing == 0 and mine[0]["count"] == truth, "the correction is the label"


def test_only_staff_count_and_only_photos_are_accepted(client: TestClient) -> None:
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
        assert t is not None
        if s.scalar(select(User).where(User.auth_subject == "dev|viewer@demo-hvac")) is None:
            s.add(
                User(
                    tenant_id=t.id,
                    auth_subject="dev|viewer@demo-hvac",
                    email="v@d.test",
                    role="viewer",
                )
            )
    data, _ = _photo()
    viewer = {"Authorization": f"Bearer {mint('dev|viewer@demo-hvac')}"}
    assert _count(client, viewer, data).status_code == 403
    assert _count(client, OWNER, b"%PDF-1.4 not a photo", "application/pdf").status_code == 422
    assert _count(client, OWNER, b"not really a jpeg", "image/jpeg").status_code == 422
    assert (
        client.post(
            f"/stock/counts/{uuid.uuid4()}/confirm", json={"count": -1}, headers=OWNER
        ).status_code
        == 422
    )


def test_a_real_business_collects_labels_before_any_model_exists(client: TestClient) -> None:
    with service_session() as s:
        t = Tenant(
            name="Corner Shop",
            slug=f"shop-{uuid.uuid4().hex[:8]}",
            pack_id="hvac",
            status="active",
            settings={"pack_id": "hvac", "channels": {}},
        )
        s.add(t)
        s.flush()
        sub = f"dev|owner@{t.slug}"
        s.add(User(tenant_id=t.id, auth_subject=sub, email=f"o@{t.slug}.test", role="owner"))
    shop = {"Authorization": f"Bearer {mint(sub)}"}
    data, truth = _photo(7)
    row = _count(client, shop, data).json()
    assert row["predicted"] is None, "a synthetic model is never used for a real business"
    r = client.post(f"/stock/counts/{row['id']}/confirm", json={"count": truth}, headers=shop)
    assert r.json()["confirmed"] == truth
