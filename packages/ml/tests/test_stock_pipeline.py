"""Stock-counter training data and pipeline. The training test needs PyTorch, which only the
vision CI job and training machines install (packages/ml/stock-requirements.txt)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from novaxis_ml.stock.data import density_target, read_labels
from novaxis_ml.stock.synthetic import write


def test_labels_are_checked_and_each_item_adds_exactly_one_to_the_map(tmp_path: Path) -> None:
    (tmp_path / "labels.jsonl").write_text(
        json.dumps({"image": "a.jpg", "count": 2, "points": [[10, 10], [600, 400]]})
        + "\n"
        + json.dumps({"image": "b.jpg", "count": 5})
        + "\n"
    )
    a, b = read_labels(tmp_path)
    assert a.count == 2 and a.points == [(10.0, 10.0), (600.0, 400.0)]
    assert b.count == 5 and b.points is None, "a count alone is a valid label"
    assert abs(float(density_target(a.points, (640, 480)).sum()) - 2.0) < 1e-4
    (tmp_path / "labels.jsonl").write_text(
        json.dumps({"image": "c.jpg", "count": 3, "points": [[1, 1]]})
    )
    with pytest.raises(ValueError, match="disagree"):
        read_labels(tmp_path)


def test_synthetic_shelves_have_as_many_points_as_items(tmp_path: Path) -> None:
    write(tmp_path, 5, seed=3)
    samples = read_labels(tmp_path)
    assert len(samples) == 5 and all(s.image.exists() for s in samples)
    assert all(s.points is not None and len(s.points) == s.count for s in samples)


def test_training_exports_a_network_the_server_runs_identically(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("onnx")
    from novaxis_core.stock_count import StockCounter
    from novaxis_ml.stock.train import train

    write(tmp_path / "photos", 48, seed=5)
    report = train(tmp_path / "photos", tmp_path / "out" / "counter", epochs=2, label="synthetic")
    assert report["onnx_max_difference"] < 1e-4, "ONNX Runtime matches PyTorch"
    assert {"mae", "within_1", "within_10pct"} <= set(report["model"])
    meta = json.loads((tmp_path / "out" / "counter.json").read_text())
    assert meta["data"] == "synthetic" and meta["input_hw"] == [192, 256]
    counter = StockCounter(tmp_path / "out" / "counter.onnx", meta)
    photo = (tmp_path / "photos" / "shelf_00000.jpg").read_bytes()
    r = counter.count(photo)
    assert r.synthetic and r.count >= 0 and np.isfinite(r.raw)
