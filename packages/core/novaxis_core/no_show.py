"""Live no-show scoring from a trained model file, in plain Python.

The model is logistic regression, trained in `packages/ml` and exported as JSON: a weight
per input. Scoring is a weighted sum passed through a sigmoid, so it needs no ML library on
the server, and every score can say *why*: the inputs that pushed it up most.

A model trained on synthetic data (to prove the pipeline) is only ever shown to demo-*
businesses, labelled as a demo, never to a real business.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from novaxis_core.features import CATEGORICAL, NUMERIC

DEFAULT_MODEL = Path(__file__).parent / "ml_models" / "no_show.json"


@dataclass(frozen=True)
class Risk:
    score: float
    level: str
    reasons: list[str]


def _reason(name: str, value: Any, contribution: float) -> str:
    if name == "lead_days":
        return f"booked {value:g} days ahead"
    if name == "confirmed":
        return "not confirmed by the customer" if not value else "confirmed by the customer"
    if name == "prior_no_shows":
        return f"missed {int(value)} earlier appointment(s)" if value else "no missed appointments"
    if name == "prior_attended":
        return f"came to {int(value)} earlier appointment(s)" if value else "first visit"
    if name == "hour":
        return f"at {int(value):02d}:00"
    if name == "weekday":
        return f"on a {str(value).capitalize()}"
    if name == "channel":
        return f"booked by {str(value).replace('_', ' ')}"
    if name == "service_code":
        return f"service: {str(value).replace('_', ' ')}"
    return f"{name}: {value}"


class NoShowModel:
    def __init__(self, spec: dict[str, Any]) -> None:
        if spec.get("kind") != "logistic_regression":
            raise ValueError("unsupported no-show model kind")
        self.spec = spec
        self.synthetic = spec.get("data") != "real"
        self.thresholds = spec.get("thresholds") or {"medium": 0.25, "high": 0.45}

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

    def risk(self, x: dict[str, Any]) -> Risk:
        p = self.probability(x)
        level = (
            "high"
            if p >= self.thresholds["high"]
            else "medium"
            if p >= self.thresholds["medium"]
            else "low"
        )
        pushes = [(c, n) for n, c in self.contributions(x).items() if c > 0.05]
        top = sorted(pushes, reverse=True)[:3]
        reasons = [_reason(n, x[n], c) for c, n in top]
        if self.synthetic:
            reasons.append("demo model trained on synthetic data")
        return Risk(round(p, 3), level, reasons)


@lru_cache(maxsize=4)
def load(path: str | None = None) -> NoShowModel | None:
    p = Path(path) if path else DEFAULT_MODEL
    if not p.exists():
        return None
    return NoShowModel(json.loads(p.read_text()))


def model_for(tenant_slug: str) -> NoShowModel | None:
    """The model a business may see: none until one exists; a synthetic one only for demos."""
    m = load()
    if m is None or (m.synthetic and not tenant_slug.startswith("demo-")):
        return None
    return m
