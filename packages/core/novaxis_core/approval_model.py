"""Will staff approve this proposal as written? Live scoring and the shadow report.

Same method as no_show.py: logistic regression trained in `packages/ml`, exported as JSON,
scored here in plain Python, and every prediction says why. It is advice only: nothing is
approved by the model. The prediction is stored on the proposal when it starts waiting, so
the shadow report can later compare what the model said with what staff decided, which is
the evidence needed before anyone considers letting it approve things (docs/ml.md).

A model trained on synthetic data is only ever shown to demo-* businesses.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.approval_features import CATEGORICAL, DECISIONS, NUMERIC, features, input_for
from novaxis_core.models import ActionProposal, Approval, Tenant

log = logging.getLogger("novaxis.approval_model")

DEFAULT_MODEL = Path(__file__).parent / "ml_models" / "approvals.json"
SHADOW_THRESHOLDS = (0.8, 0.9, 0.95)


def _reason(name: str, value: Any) -> str:
    if name == "prior_rate":
        return f"this business approved {value:.0%} of these before"
    if name == "prior_decisions":
        return f"{int(value)} earlier decisions on this kind" if value else "no earlier decisions"
    if name == "has_money":
        return "mentions money" if value else "no money mentioned"
    if name == "has_time":
        return "mentions a day or time" if value else "no day or time mentioned"
    if name == "text_len":
        return "long message" if value >= 3 else "short message"
    if name == "conv_messages":
        return f"{int(value)} message(s) so far"
    if name == "customer_messages":
        return f"customer wrote {int(value)} time(s)"
    if name == "hour":
        return f"proposed at {int(value):02d}:00"
    if name == "weekday":
        return f"proposed on a {str(value).capitalize()}"
    if name == "kind":
        return str(value).replace("_", " ")
    if name == "origin":
        return f"from: {str(value).replace('_', ' ')}"
    if name == "gate_reason":
        return {
            "tenant_override": "held by the business's own rule",
            "pack_rule": "held by the trade's rule",
            "default": "held by default",
        }.get(str(value), "held for another reason")
    if name == "channel":
        return f"on {str(value).replace('_', ' ')}"
    return f"{name}: {value}"


class ApprovalModel:
    def __init__(self, spec: dict[str, Any]) -> None:
        if spec.get("kind") != "logistic_regression":
            raise ValueError("unsupported approval model kind")
        self.spec = spec
        self.synthetic = spec.get("data") != "real"
        self.thresholds = spec.get("thresholds") or {"likely": 0.8, "unlikely": 0.5}

    def contributions(self, x: dict[str, Any]) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in NUMERIC:
            p = self.spec["numeric"][name]
            std = float(p["std"]) or 1.0
            out[name] = float(p["weight"]) * (float(x[name]) - float(p["mean"])) / std
        for name in CATEGORICAL:
            out[name] = float(self.spec["categorical"].get(name, {}).get(str(x[name]), 0.0))
        return out

    def probability(self, x: dict[str, Any]) -> float:
        z = float(self.spec["intercept"]) + sum(self.contributions(x).values())
        return 1.0 / (1.0 + math.exp(-z))

    def predict(self, x: dict[str, Any]) -> dict[str, Any]:
        p = self.probability(x)
        level = (
            "likely"
            if p >= self.thresholds["likely"]
            else "unlikely"
            if p < self.thresholds["unlikely"]
            else "unsure"
        )
        c = self.contributions(x)
        top = sorted(((abs(v), n, v > 0) for n, v in c.items() if abs(v) > 0.1), reverse=True)[:3]
        reasons = [f"{'+' if up else '-'} {_reason(n, x[n])}" for _, n, up in top]
        if self.synthetic:
            reasons.append("demo model trained on synthetic data")
        return {
            "p": round(p, 3),
            "level": level,
            "reasons": reasons,
            "model": str(self.spec.get("trained_at", "")),
            "data": "synthetic" if self.synthetic else "real",
        }


@lru_cache(maxsize=4)
def load(path: str | None = None) -> ApprovalModel | None:
    p = Path(path) if path else DEFAULT_MODEL
    if not p.exists():
        return None
    return ApprovalModel(json.loads(p.read_text()))


def model_for(tenant_slug: str) -> ApprovalModel | None:
    """The model a business may see: none until one exists; a synthetic one only for demos."""
    m = load()
    if m is None or (m.synthetic and not tenant_slug.startswith("demo-")):
        return None
    return m


def record_prediction(session: Session, tenant: Tenant, p: ActionProposal) -> None:
    """Store the prediction on a proposal that is starting to wait. Advice only, so a
    failure here is logged and never stops the proposal reaching staff."""
    m = model_for(tenant.slug)
    if m is None:
        return
    try:
        # A savepoint: if anything here fails, even in the database, only this is undone
        # and the caller's transaction (the proposal, the staff alert) carries on.
        with session.begin_nested():
            p.prediction = m.predict(features(input_for(session, tenant, p)))
    except Exception:  # noqa: BLE001 - advice must never block the approval queue
        log.exception("approval prediction failed for proposal %s", p.id)


def shadow_report(session: Session) -> dict[str, Any]:
    """For this business (tenant session): of the decided proposals that had a prediction,
    what would "approve automatically above X%" have done? Nothing is approved by this."""
    rows = session.execute(
        select(ActionProposal.prediction, Approval.decision)
        .join(Approval, Approval.proposal_id == ActionProposal.id)
        .where(ActionProposal.prediction.is_not(None), Approval.decision.in_(DECISIONS))
    ).all()
    scored = [(float(pred["p"]), decision == "approve") for pred, decision in rows]
    n = len(scored)
    approved = sum(1 for _, a in scored if a)
    out: dict[str, Any] = {
        "decided_with_prediction": n,
        "staff_approved": approved,
        "agreement": round(sum(1 for p, a in scored if (p >= 0.5) == a) / n, 3) if n else None,
        "thresholds": [],
    }
    for t in SHADOW_THRESHOLDS:
        picked = [a for p, a in scored if p >= t]
        wrong = sum(1 for a in picked if not a)
        out["thresholds"].append(
            {
                "threshold": t,
                "would_auto_approve": len(picked),
                "of_which_staff_did_not_approve": wrong,
                "precision": round((len(picked) - wrong) / len(picked), 3) if picked else None,
                "share_of_queue": round(len(picked) / n, 3) if n else None,
            }
        )
    return out
