"""Train, evaluate and export the no-show model.

    uv run python -m novaxis_ml.no_show train --source synthetic
    uv run python -m novaxis_ml.no_show train --source db          # real recorded outcomes
    uv run python -m novaxis_ml.no_show export --out rows.csv      # the training table

Method (docs/ml.md): logistic regression, because it can be scored without ML libraries on
the server and explains every score. A gradient-boosted model is trained on the same split
as a challenger; if it wins clearly, the report says so. Evaluation is on the most recent 20%
of bookings (a time split, as in real use: train on the past, predict the future). The
exported model is then refit on all rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from novaxis_core.features import CATEGORICAL, NUMERIC, LabelledRow
from novaxis_core.no_show import DEFAULT_MODEL

MIN_ROWS = 200
MIN_NO_SHOWS = 20


class NotEnoughDataError(ValueError):
    pass


def fit_encoding(
    rows: list[dict[str, Any]],
    numeric: tuple[str, ...] = NUMERIC,
    categorical: tuple[str, ...] = CATEGORICAL,
) -> dict[str, Any]:
    enc: dict[str, Any] = {"numeric": {}, "categorical": {}}
    for name in numeric:
        v = np.array([float(r[name]) for r in rows])
        enc["numeric"][name] = {"mean": float(v.mean()), "std": float(v.std()) or 1.0}
    for name in categorical:
        enc["categorical"][name] = sorted({str(r[name]) for r in rows})
    return enc


def encode(rows: list[dict[str, Any]], enc: dict[str, Any]) -> np.ndarray:
    """Standardised numbers, then one column per category seen in training."""
    cols: list[np.ndarray] = []
    for name in enc["numeric"]:
        p = enc["numeric"][name]
        cols.append((np.array([float(r[name]) for r in rows]) - p["mean"]) / p["std"])
    for name in enc["categorical"]:
        for value in enc["categorical"][name]:
            cols.append(np.array([1.0 if str(r[name]) == value else 0.0 for r in rows]))
    return np.column_stack(cols)


def _logreg() -> LogisticRegression:
    return LogisticRegression(C=1.0, max_iter=2000)


def to_spec(lr: LogisticRegression, enc: dict[str, Any]) -> dict[str, Any]:
    w = lr.coef_[0]
    i = 0
    numeric: dict[str, Any] = {}
    for name in enc["numeric"]:
        numeric[name] = {**enc["numeric"][name], "weight": float(w[i])}
        i += 1
    categorical: dict[str, dict[str, float]] = {}
    for name in enc["categorical"]:
        categorical[name] = {}
        for value in enc["categorical"][name]:
            categorical[name][value] = float(w[i])
            i += 1
    return {
        "kind": "logistic_regression",
        "intercept": float(lr.intercept_[0]),
        "numeric": numeric,
        "categorical": categorical,
    }


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def train(rows: list[LabelledRow], data: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (model spec to save, evaluation report). `data` is "real" or "synthetic"."""
    y_all = np.array([r.no_show for r in rows])
    if len(rows) < MIN_ROWS or int(y_all.sum()) < MIN_NO_SHOWS:
        raise NotEnoughDataError(
            f"need at least {MIN_ROWS} bookings with an outcome and {MIN_NO_SHOWS} no-shows; "
            f"have {len(rows)} and {int(y_all.sum())}"
        )
    cut = int(len(rows) * 0.8)
    train_rows, test_rows = rows[:cut], rows[cut:]
    y_tr, y_te = y_all[:cut], y_all[cut:]
    if len(set(y_te.tolist())) < 2:
        raise NotEnoughDataError("the most recent 20% of bookings has only one outcome")
    enc = fit_encoding([r.features for r in train_rows])
    x_tr = encode([r.features for r in train_rows], enc)
    x_te = encode([r.features for r in test_rows], enc)

    lr = _logreg().fit(x_tr, y_tr)
    gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=0)
    gb.fit(x_tr, y_tr)
    base_rate = float(y_tr.mean())
    report: dict[str, Any] = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data": data,
        "rows": len(rows),
        "train_rows": cut,
        "test_rows": len(rows) - cut,
        "no_show_rate": round(float(y_all.mean()), 4),
        "logistic_regression": _metrics(y_te, lr.predict_proba(x_te)[:, 1]),
        "gradient_boosting": _metrics(y_te, gb.predict_proba(x_te)[:, 1]),
        "always_average": _metrics(y_te, np.full(len(y_te), base_rate)),
    }
    gap = report["gradient_boosting"]["auc"] - report["logistic_regression"]["auc"]
    report["challenger_note"] = (
        f"gradient boosting beats the shipped model by {gap:.3f} AUC: worth serving it"
        if gap > 0.03
        else "logistic regression is as good as gradient boosting here; ship it"
    )

    # The shipped model learns from every row.
    enc_all = fit_encoding([r.features for r in rows])
    final = _logreg().fit(encode([r.features for r in rows], enc_all), y_all)
    spec = to_spec(final, enc_all)
    spec.update(
        {
            "data": data,
            "trained_at": report["trained_at"],
            "rows": len(rows),
            "metrics": report["logistic_regression"],
            "thresholds": {
                "medium": round(min(base_rate * 1.5, 0.9), 3),
                "high": round(min(base_rate * 2.5, 0.95), 3),
            },
        }
    )
    return spec, report


def _rows_from_db() -> list[LabelledRow]:
    from novaxis_core.features import labelled_rows
    from novaxis_db.session import service_session

    with service_session() as s:
        return labelled_rows(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="novaxis_ml.no_show")
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
            w.writerow(["starts_at", *NUMERIC, *CATEGORICAL, "no_show"])
            for r in rows:
                w.writerow(
                    [
                        r.starts_at.isoformat(),
                        *(r.features[k] for k in (*NUMERIC, *CATEGORICAL)),
                        r.no_show,
                    ]
                )
        print(f"wrote {len(rows)} rows to {args.out}")
        return 0

    if args.source == "synthetic":
        from novaxis_ml.synthetic import generate

        rows = generate()
    else:
        rows = _rows_from_db()
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
