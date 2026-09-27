"""Stock-count datasets: a folder of photos and a `labels.jsonl`.

One line per photo:

    {"image": "shelf_001.jpg", "count": 23}
    {"image": "shelf_002.jpg", "count": 7, "points": [[120, 88], [141, 90], ...]}

`count` is required: the true number of items, as written down when the photo was taken.
`points` is optional: one click on the centre of each item, in the photo's own pixels.
Photos with points teach the network *where* items are and train much faster; photos
with only a count still help. The platform's Stock page produces this format (staff
confirm or correct each count), and `export` in `train.py` writes it.

Everything here needs only numpy and Pillow, so labelling tools work without PyTorch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from novaxis_core.vision import INPUT_HW, MEAN, STD, STRIDE, load_image

__all__ = ["INPUT_HW", "MEAN", "STD", "STRIDE", "load_image"]


@dataclass(frozen=True)
class Sample:
    image: Path
    count: int
    points: list[tuple[float, float]] | None


def read_labels(folder: Path) -> list[Sample]:
    out: list[Sample] = []
    for n, line in enumerate((folder / "labels.jsonl").read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        count = int(row["count"])
        points = [(float(x), float(y)) for x, y in row["points"]] if row.get("points") else None
        if count < 0 or (points is not None and len(points) != count):
            raise ValueError(f"labels.jsonl line {n}: count and number of points disagree")
        out.append(Sample(folder / row["image"], count, points))
    return out


def density_target(points: list[tuple[float, float]], size: tuple[int, int]) -> np.ndarray:
    """A map at 1/STRIDE resolution whose cells sum to the number of items: each item
    spreads one unit of mass as a small Gaussian around its centre."""
    h, w = INPUT_HW[0] // STRIDE, INPUT_HW[1] // STRIDE
    out = np.zeros((h, w), dtype=np.float32)
    ys, xs = np.mgrid[0:h, 0:w]
    sx, sy = w / size[0], h / size[1]
    for px, py in points:
        cx, cy = px * sx - 0.5, py * sy - 0.5
        g = np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * 0.8**2))
        total = g.sum()
        if total > 0:
            out += g / total
    return out
