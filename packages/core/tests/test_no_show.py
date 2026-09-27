"""Live no-show scoring: plain-language reasons, levels, and synthetic models kept to demos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from novaxis_core import no_show
from novaxis_core.features import Booking, features
from novaxis_core.no_show import NoShowModel

SPEC = {
    "kind": "logistic_regression",
    "data": "real",
    "intercept": -2.0,
    "thresholds": {"medium": 0.25, "high": 0.45},
    "numeric": {
        "lead_days": {"mean": 10, "std": 10, "weight": 0.8},
        "hour": {"mean": 12, "std": 3, "weight": 0.0},
        "confirmed": {"mean": 0.5, "std": 0.5, "weight": -0.7},
        "prior_attended": {"mean": 1, "std": 1, "weight": -0.2},
        "prior_no_shows": {"mean": 0.3, "std": 0.6, "weight": 0.6},
    },
    "categorical": {"weekday": {"mon": 0.3}, "channel": {"webchat": 0.2}},
}


def _x(**kw: object) -> dict[str, object]:
    start = datetime(2026, 10, 5, 9, tzinfo=UTC)  # a Monday
    b = {
        "starts_at": start,
        "booked_at": start - timedelta(days=40),
        "service_code": "checkup",
        "channel": "webchat",
        "pack_id": "dental",
        "confirmed": False,
        "prior_attended": 0,
        "prior_no_shows": 2,
        **kw,
    }
    return features(Booking(**b))  # type: ignore[arg-type]


def test_risky_booking_is_high_with_the_reasons_that_pushed_it() -> None:
    r = NoShowModel(SPEC).risk(_x())
    assert r.level == "high"
    assert r.reasons[:3] == [
        "booked 40 days ahead",
        "missed 2 earlier appointment(s)",
        "not confirmed by the customer",
    ]
    safe = NoShowModel(SPEC).risk(
        _x(
            booked_at=datetime(2026, 10, 4, tzinfo=UTC),
            confirmed=True,
            prior_no_shows=0,
            prior_attended=4,
        )
    )
    assert safe.level == "low" and safe.score < r.score


def test_a_synthetic_model_is_only_ever_shown_to_demo_businesses(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    path = tmp_path / "m.json"
    path.write_text(json.dumps({**SPEC, "data": "synthetic"}))
    monkeypatch.setattr(no_show, "DEFAULT_MODEL", path)
    no_show.load.cache_clear()
    try:
        assert no_show.model_for("demo-dental") is not None
        assert no_show.model_for("smiles-dental") is None
        assert "synthetic" in no_show.model_for("demo-dental").risk(_x()).reasons[-1]  # type: ignore[union-attr]
        path.write_text(json.dumps(SPEC))
        no_show.load.cache_clear()
        assert no_show.model_for("smiles-dental") is not None, "a real model serves everyone"
        monkeypatch.setattr(no_show, "DEFAULT_MODEL", tmp_path / "missing.json")
        no_show.load.cache_clear()
        assert no_show.model_for("demo-dental") is None
    finally:
        no_show.load.cache_clear()
