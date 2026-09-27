"""Count items in a stock photo with the trained network (ONNX Runtime, no PyTorch).

The network outputs a density map; the count is its sum. Local peaks in the map are
returned as approximate item positions so staff can see *what* was counted before they
confirm or correct it (every correction is a training label, docs/ml.md).

A network trained on synthetic shelves is only ever used for demo-* businesses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from novaxis_core.vision import load_image

MODEL_DIR = Path(__file__).parent / "ml_models"


@dataclass(frozen=True)
class StockCount:
    count: int
    raw: float
    points: list[tuple[int, int]]  # approximate item centres, in the photo's pixels
    synthetic: bool
    model: str


class StockCounter:
    def __init__(self, onnx_path: Path, meta: dict[str, Any]) -> None:
        import onnxruntime as ort

        self.meta = meta
        self.synthetic = meta.get("data") != "real"
        self.hw = (int(meta["input_hw"][0]), int(meta["input_hw"][1]))
        self.stride = int(meta["stride"])
        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

    def count(self, photo: bytes) -> StockCount:
        arr, (w, h) = load_image(photo, self.hw, tuple(self.meta["mean"]), tuple(self.meta["std"]))
        dens = self.session.run(None, {"image": arr[None]})[0][0, 0]
        raw = float(dens.sum())
        return StockCount(
            count=max(0, round(raw)),
            raw=round(raw, 2),
            points=_peaks(dens, w / dens.shape[1], h / dens.shape[0]),
            synthetic=self.synthetic,
            model=str(self.meta.get("trained_at", "")),
        )


def _peaks(dens: np.ndarray, sx: float, sy: float, floor: float = 0.1) -> list[tuple[int, int]]:
    """Cells that are the largest in their 3x3 neighbourhood and hold enough mass."""
    padded = np.pad(dens, 1, constant_values=-1.0)
    neigh = np.max(
        np.stack(
            [
                padded[dy : dy + dens.shape[0], dx : dx + dens.shape[1]]
                for dy in range(3)
                for dx in range(3)
            ]
        ),
        axis=0,
    )
    ys, xs = np.nonzero((dens >= neigh) & (dens >= floor))
    return [(int((x + 0.5) * sx), int((y + 0.5) * sy)) for y, x in zip(ys, xs, strict=True)]


@lru_cache(maxsize=2)
def load(name: str = "stock_counter") -> StockCounter | None:
    onnx_path, meta_path = MODEL_DIR / f"{name}.onnx", MODEL_DIR / f"{name}.json"
    if not onnx_path.exists() or not meta_path.exists():
        return None
    return StockCounter(onnx_path, json.loads(meta_path.read_text()))


def counter_for(tenant_slug: str) -> StockCounter | None:
    """The counter a business may use: none until one exists; a synthetic one only for demos."""
    c = load()
    if c is None or (c.synthetic and not tenant_slug.startswith("demo-")):
        return None
    return c
