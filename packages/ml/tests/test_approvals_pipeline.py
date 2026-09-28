"""The approval-learning pipeline: training recovers planted effects and is compared with
the business's own history, the exported file scores exactly like the trained model, too
little data is refused, features carry no message text, and a proposal's history counts
only decisions made before it existed."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import select

from novaxis_core.approval_features import (
    CATEGORICAL,
    NUMERIC,
    ProposalInput,
    features,
    labelled_rows,
)
from novaxis_core.approval_model import ApprovalModel
from novaxis_core.models import ActionProposal, Approval, Tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session
from novaxis_ml.approvals import generate, train
from novaxis_ml.no_show import NotEnoughDataError, _logreg, encode, fit_encoding, to_spec


def test_training_recovers_the_planted_effects_and_is_compared_with_history() -> None:
    spec, report = train(generate(3000), "synthetic")
    lr = report["logistic_regression"]
    assert lr["auc"] > report["history_only"]["auc"] > 0.5
    assert report["verdict"].startswith("beats the business's own history")
    w = {k: v["weight"] for k, v in spec["numeric"].items()}
    assert w["has_money"] < 0 and w["text_len"] < 0 and w["prior_rate"] > 0
    kinds = spec["categorical"]["kind"]
    assert kinds["confirm_appointment"] > kinds["cancel_appointment"] > kinds["quote_price"]
    assert spec["categorical"]["gate_reason"]["tenant_override"] < 0
    assert [t["threshold"] for t in report["precision_at"]] == [0.8, 0.9, 0.95]
    assert spec["data"] == "synthetic" and spec["thresholds"] == {"likely": 0.8, "unlikely": 0.5}


def test_the_exported_file_scores_exactly_like_the_trained_model() -> None:
    rows = generate(1200, seed=5)
    feats = [r.features for r in rows]
    enc = fit_encoding(feats, NUMERIC, CATEGORICAL)
    x = encode(feats, enc)
    lr = _logreg().fit(x, np.array([r.approved for r in rows]))
    served = ApprovalModel({**to_spec(lr, enc), "data": "synthetic"})
    expected = lr.predict_proba(x[:200])[:, 1]
    got = np.array([served.probability(f) for f in feats[:200]])
    assert np.max(np.abs(expected - got)) < 1e-9, "no train/serve skew"


def test_too_little_data_is_refused_not_trained() -> None:
    with pytest.raises(NotEnoughDataError, match="need at least"):
        train(generate(120), "real")


def test_features_carry_no_message_text() -> None:
    x = features(
        ProposalInput(
            kind="reply",
            params={"text": "Hi Sam at 12 Oak Road, it costs £85 on Monday at 9am"},
            reason="workflow:chase_24h: tenant override (raised)",
            created_at=datetime(2026, 9, 28, 9, tzinfo=UTC),
            channel="whatsapp",
            pack_id="hvac",
            conv_messages=4,
            customer_messages=2,
            prior_approved=0,
            prior_decided=0,
        )
    )
    assert x["has_money"] == 1.0 and x["has_time"] == 1.0
    assert x["origin"] == "workflow" and x["gate_reason"] == "tenant_override"
    assert x["prior_rate"] == 0.5, "no history means no idea, not a verdict"
    words = {str(v) for v in x.values() if isinstance(v, str)}
    assert words == {"reply", "workflow", "tenant_override", "whatsapp", "hvac", "mon"}


def test_history_counts_only_decisions_made_before_the_proposal(migrated: str) -> None:
    with service_session(migrated) as s:
        seed(s)
        t = s.scalar(select(Tenant).where(Tenant.slug == "demo-restoration"))
        assert t is not None
        day = [datetime(2001, 1, d, 9, tzinfo=UTC) for d in (1, 2, 3, 4)]
        first = ActionProposal(
            tenant_id=t.id,
            kind="cancel_appointment",
            params={"appointment_id": "x"},
            risk="medium",
            state="rejected",
            reason="model proposal: default",
            created_at=day[0],
        )
        second = ActionProposal(
            tenant_id=t.id,
            kind="cancel_appointment",
            params={"appointment_id": "y"},
            risk="medium",
            state="approved",
            reason="model proposal: default",
            created_at=day[2],
        )
        s.add_all([first, second])
        s.flush()
        s.add_all(
            [
                Approval(
                    tenant_id=t.id, proposal_id=first.id, decision="reject", created_at=day[1]
                ),
                Approval(
                    tenant_id=t.id, proposal_id=second.id, decision="approve", created_at=day[3]
                ),
            ]
        )
        s.flush()
        rows = {r.created_at: r for r in labelled_rows(s, [t.id])}
    assert rows[day[0]].approved == 0 and rows[day[0]].features["prior_decisions"] == 0
    later = rows[day[2]]
    assert later.approved == 1 and later.features["prior_decisions"] == 1
    assert later.features["prior_rate"] == round(1 / 3, 4), "one earlier reject, smoothed"
