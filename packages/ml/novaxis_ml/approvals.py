"""Train, evaluate and export the approval model: will staff approve a proposal as written?

    uv run python -m novaxis_ml.approvals train --source synthetic
    uv run python -m novaxis_ml.approvals train --source db          # real staff decisions
    uv run python -m novaxis_ml.approvals export --out rows.csv      # the training table

Labels are free: every approve (1), reject or edit (0) staff make in the approval queue.
Method as for no-shows (docs/ml.md): logistic regression, exported to JSON and scored in
plain Python with reasons; gradient boosting trained on the same split as a challenger;
evaluated on the most recent 20% of decisions. Two things are reported that decide whether
the model is worth anything:

- against "history only" (this business's past approval rate for the kind): if the model
  cannot beat that, it adds nothing;
- precision at 80/90/95%: of the proposals it would call safe, how many staff approved.
  That is the number that would have to be near 100% before anyone lets it approve.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from novaxis_core.approval_features import (
    CATEGORICAL,
    NUMERIC,
    LabelledRow,
    ProposalInput,
    features,
)
from novaxis_core.approval_model import DEFAULT_MODEL, SHADOW_THRESHOLDS
from novaxis_ml.no_show import NotEnoughDataError, _logreg, encode, fit_encoding, to_spec

MIN_ROWS = 200
MIN_EACH = 20
THRESHOLDS = {"likely": 0.8, "unlikely": 0.5}


# --- synthetic decisions --------------------------------------------------------------
# Not a model of real staff. Planted effects (on the log-odds of "approved as written"),
# so tests can check training recovers them:
#   base +1.4; cancel -0.9, quote -1.2, reschedule -0.4, confirm +0.6;
#   mentions money -1.0; each 100 characters of text -0.25;
#   held by the business's own rule -0.5; the business's past approval rate +3 * (rate - 0.5)

KINDS = {
    "confirm_appointment": 0.6,
    "propose_appointment": 0.2,
    "reschedule_appointment": -0.4,
    "cancel_appointment": -0.9,
    "quote_price": -1.2,
    "reply": 0.0,
}
PACKS = ["hvac", "dental", "restoration"]
CHANNELS = ["webchat", "twilio_sms", "email", "whatsapp"]
WORDS = "please thanks booking visit engineer team slot window arrive call soon".split()


def true_logit(x: dict[str, Any]) -> float:
    z = 1.4 + KINDS.get(str(x["kind"]), 0.0)
    z += -1.0 * x["has_money"] - 0.25 * x["text_len"]
    z += -0.5 * (x["gate_reason"] == "tenant_override")
    z += 3.0 * (x["prior_rate"] - 0.5)
    return float(z)


def generate(n: int = 3000, seed: int = 11) -> list[LabelledRow]:
    rng = random.Random(seed)
    start = datetime(2025, 3, 3, 8, tzinfo=UTC)
    rows: list[LabelledRow] = []
    for _ in range(n):
        kind = rng.choice(list(KINDS))
        text = " ".join(rng.choice(WORDS) for _ in range(rng.randrange(3, 60)))
        if rng.random() < 0.2:
            text += " it costs £85"
        params: dict[str, Any] = {"text": text} if kind == "reply" else {"notes": text}
        decided = rng.choice([0, 0, 1, 3, 6, 10, 20, 40])
        approved = sum(rng.random() < 0.5 + 0.4 * KINDS[kind] for _ in range(decided))
        origin = rng.choice(["model proposal", "intake complete", "workflow:chase_24h"])
        rule = rng.choice(["default", "default", "pack rule", "tenant override"])
        pi = ProposalInput(
            kind=kind,
            params=params,
            reason=f"{origin}: {rule}",
            created_at=start + timedelta(hours=rng.randrange(0, 24 * 500)),
            channel=rng.choice(CHANNELS),
            pack_id=rng.choice(PACKS),
            conv_messages=rng.randrange(1, 30),
            customer_messages=rng.randrange(1, 12),
            prior_approved=min(approved, decided),
            prior_decided=decided,
            timezone="UTC",
        )
        x = features(pi)
        p = 1 / (1 + math.exp(-true_logit(x)))
        rows.append(LabelledRow(pi.created_at, x, int(rng.random() < p)))
    rows.sort(key=lambda r: r.created_at)
    return rows


# --- training --------------------------------------------------------------------------


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    return round(float(roc_auc_score(y, p)), 4)


def precision_at(y: np.ndarray, p: np.ndarray) -> list[dict[str, Any]]:
    out = []
    for t in SHADOW_THRESHOLDS:
        picked = p >= t
        n = int(picked.sum())
        out.append(
            {
                "threshold": t,
                "would_auto_approve": n,
                "precision": round(float(y[picked].mean()), 4) if n else None,
                "share_of_queue": round(n / len(y), 4),
            }
        )
    return out


def train(rows: list[LabelledRow], data: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (model spec to save, evaluation report). `data` is "real" or "synthetic"."""
    y_all = np.array([r.approved for r in rows])
    yes = int(y_all.sum())
    if len(rows) < MIN_ROWS or min(yes, len(rows) - yes) < MIN_EACH:
        raise NotEnoughDataError(
            f"need at least {MIN_ROWS} staff decisions with {MIN_EACH} approvals and "
            f"{MIN_EACH} rejections or edits; have {len(rows)} ({yes} approved)"
        )
    cut = int(len(rows) * 0.8)
    train_rows, test_rows = rows[:cut], rows[cut:]
    y_tr, y_te = y_all[:cut], y_all[cut:]
    if len(set(y_te.tolist())) < 2:
        raise NotEnoughDataError("the most recent 20% of decisions has only one outcome")
    enc = fit_encoding([r.features for r in train_rows], NUMERIC, CATEGORICAL)
    x_tr = encode([r.features for r in train_rows], enc)
    x_te = encode([r.features for r in test_rows], enc)

    lr = _logreg().fit(x_tr, y_tr)
    gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=0)
    gb.fit(x_tr, y_tr)
    p_lr = lr.predict_proba(x_te)[:, 1]
    history = np.array([float(r.features["prior_rate"]) for r in test_rows])
    report: dict[str, Any] = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data": data,
        "rows": len(rows),
        "train_rows": cut,
        "test_rows": len(rows) - cut,
        "approval_rate": round(float(y_all.mean()), 4),
        "logistic_regression": {
            "auc": _auc(y_te, p_lr),
            "brier": round(float(brier_score_loss(y_te, p_lr)), 4),
        },
        "gradient_boosting": {"auc": _auc(y_te, gb.predict_proba(x_te)[:, 1])},
        "history_only": {"auc": _auc(y_te, history)},
        "precision_at": precision_at(y_te, p_lr),
    }
    gain = report["logistic_regression"]["auc"] - report["history_only"]["auc"]
    report["verdict"] = (
        f"beats the business's own history by {gain:.3f} AUC"
        if gain > 0.02
        else "no better than the business's own history: do not rely on it"
    )

    enc_all = fit_encoding([r.features for r in rows], NUMERIC, CATEGORICAL)
    final = _logreg().fit(encode([r.features for r in rows], enc_all), y_all)
    spec = to_spec(final, enc_all)
    spec.update(
        {
            "data": data,
            "trained_at": report["trained_at"],
            "rows": len(rows),
            "metrics": report["logistic_regression"],
            "precision_at": report["precision_at"],
            "thresholds": THRESHOLDS,
        }
    )
    return spec, report


def _rows_from_db() -> list[LabelledRow]:
    from novaxis_core.approval_features import labelled_rows
    from novaxis_db.session import service_session

    with service_session() as s:
        return labelled_rows(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="novaxis_ml.approvals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--source", choices=["db", "synthetic"], required=True)
    t.add_argument("--out", default=str(DEFAULT_MODEL))
    e = sub.add_parser("export")
    e.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "export":
        rows = _rows_from_db()
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["created_at", *NUMERIC, *CATEGORICAL, "approved"])
            for r in rows:
                w.writerow(
                    [
                        r.created_at.isoformat(),
                        *(r.features[k] for k in (*NUMERIC, *CATEGORICAL)),
                        r.approved,
                    ]
                )
        print(f"wrote {len(rows)} rows to {args.out}")
        return 0

    rows = generate() if args.source == "synthetic" else _rows_from_db()
    try:
        spec, report = train(rows, "synthetic" if args.source == "synthetic" else "real")
    except NotEnoughDataError as exc:
        print(f"not trained: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    print(f"model written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
