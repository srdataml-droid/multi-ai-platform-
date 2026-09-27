"""The no-show pipeline: training recovers planted effects, the exported file scores exactly
like the trained model, too little data is refused, and training rows never leak."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from novaxis_core.features import CATEGORICAL, NUMERIC, labelled_rows
from novaxis_core.models import Appointment, Contact, Tenant
from novaxis_core.no_show import NoShowModel
from novaxis_db.seed import seed
from novaxis_db.session import service_session
from novaxis_ml.no_show import (
    NotEnoughDataError,
    _logreg,
    encode,
    fit_encoding,
    to_spec,
    train,
)
from novaxis_ml.synthetic import generate


def test_training_recovers_the_planted_effects_and_beats_guessing() -> None:
    spec, report = train(generate(4000), "synthetic")
    lr = report["logistic_regression"]
    assert lr["auc"] > 0.75 and lr["auc"] > report["always_average"]["auc"] + 0.2
    assert lr["brier"] < report["always_average"]["brier"]
    w = {k: v["weight"] for k, v in spec["numeric"].items()}
    assert w["confirmed"] < 0 and w["prior_attended"] < 0
    assert w["lead_days"] > 0 and w["prior_no_shows"] > 0
    days = spec["categorical"]["weekday"]
    assert days["mon"] > days["wed"], "Monday was planted as riskier"
    assert (
        spec["data"] == "synthetic"
        and 0 < spec["thresholds"]["medium"] < spec["thresholds"]["high"]
    )


def test_the_exported_file_scores_exactly_like_the_trained_model() -> None:
    rows = generate(1500, seed=3)
    feats = [r.features for r in rows]
    enc = fit_encoding(feats)
    x = encode(feats, enc)
    lr = _logreg().fit(x, np.array([r.no_show for r in rows]))
    served = NoShowModel({**to_spec(lr, enc), "data": "synthetic"})
    expected = lr.predict_proba(x[:200])[:, 1]
    got = np.array([served.probability(f) for f in feats[:200]])
    assert np.max(np.abs(expected - got)) < 1e-9, "no train/serve skew"


def test_too_little_data_is_refused_not_trained() -> None:
    with pytest.raises(NotEnoughDataError, match="need at least"):
        train(generate(150), "real")


def test_training_rows_use_only_earlier_outcomes_and_carry_no_identity(migrated: str) -> None:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-dental"))
        assert t is not None
        c = Contact(tenant_id=t.id, display_name="Pat Private", phones=["+447700900555"])
        s.add(c)
        s.flush()
        base = datetime.now(UTC) - timedelta(days=60)
        for i, outcome in enumerate(["no_show", "attended", "no_show"]):
            s.add(
                Appointment(
                    tenant_id=t.id,
                    contact_id=c.id,
                    starts_at=base + timedelta(days=10 * i),
                    ends_at=base + timedelta(days=10 * i, hours=1),
                    service_code="checkup",
                    status="confirmed",
                    outcome=outcome,
                    created_at=base + timedelta(days=10 * i - 7),
                )
            )
        tid = t.id
        rows = [r for r in labelled_rows(s, [tid]) if r.starts_at >= base - timedelta(seconds=1)]
    mine = rows[-3:]
    assert [r.no_show for r in mine] == [1, 0, 1]
    assert [(r.features["prior_no_shows"], r.features["prior_attended"]) for r in mine] == [
        (0, 0),
        (1, 0),
        (1, 1),
    ], "history counts only appointments before this one"
    assert mine[0].features["lead_days"] == 7
    assert set(mine[0].features) == set(NUMERIC) | set(CATEGORICAL)
    assert "Pat" not in str(mine) and "+4477" not in str(mine)
