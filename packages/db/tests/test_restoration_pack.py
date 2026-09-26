from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from novaxis_core.models import Tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session
from novaxis_packs import get_pack

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))


@pytest.fixture
def resto(migrated: str) -> Tenant:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-restoration"))
        assert t is not None
        s.expunge(t)
        return t


def test_restoration_evals_all_pass_with_scripted_model(resto: Tenant) -> None:
    from run import run_pack

    outcomes = run_pack("restoration", real=False)
    assert len(outcomes) == 5
    failed = {o.name: o.failures for o in outcomes if not o.passed}
    assert not failed, failed


def test_emergency_rule() -> None:
    check = get_pack("restoration").emergency_check
    assert check is not None
    assert check("pipe burst and water is still coming through the ceiling")
    assert check("small fire in the kitchen, still smoke now")
    assert check("the bedroom ceiling is sagging badly and looks like it's coming down")
    assert check("raw sewage backing up into the downstairs toilet")
    assert not check("we had a leak last week, plumber fixed it, carpets soaked")
    assert not check("fire damage from last month, need a quote")


def test_three_packs_on_one_core() -> None:
    from novaxis_packs import available_packs

    assert {"generic", "hvac", "dental", "restoration"} <= set(available_packs())
    r = get_pack("restoration")
    assert (
        r.service_area_field == "postcode" and "address" in r.sensitive_keys and len(r.intake) == 11
    )
