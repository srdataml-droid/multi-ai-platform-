"""Train the stock counter and export it for the API.

    python -m novaxis_ml.stock.train --data /path/to/photos --out stock_counter
        [--size tiny|mobilenet] [--pretrained] [--epochs 30]

Writes `<out>.onnx` (the network) and `<out>.json` (input size, normalisation, which data
it learned from, and held-out accuracy). Copy both into
`packages/core/novaxis_core/ml_models/` to serve them.

Evaluation: 15% of photos (fixed by seed) are never trained on. The report compares the
network against "always guess the average count", and gives mean absolute error, the share
of photos counted exactly right or within one, and within 10%.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from novaxis_ml.stock.data import (
    INPUT_HW,
    MEAN,
    STD,
    STRIDE,
    Sample,
    density_target,
    load_image,
    read_labels,
)
from novaxis_ml.stock.model import CountNet


class Photos(
    torch.utils.data.Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]]
):
    def __init__(self, samples: list[Sample], augment: bool) -> None:
        self.samples = samples
        self.augment = augment

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        s = self.samples[i]
        arr, size = load_image(s.image)
        dens = density_target(s.points, size) if s.points is not None else None
        if self.augment and random.random() < 0.5:  # mirror: a shelf flipped has the same count
            arr = arr[:, :, ::-1].copy()
            dens = dens[:, ::-1].copy() if dens is not None else None
        has_points = dens is not None
        if dens is None:
            dens = np.zeros((INPUT_HW[0] // STRIDE, INPUT_HW[1] // STRIDE), dtype=np.float32)
        return (
            torch.from_numpy(arr),
            torch.from_numpy(dens)[None],
            torch.tensor(float(s.count)),
            torch.tensor(1.0 if has_points else 0.0),
        )


def loss_fn(
    pred: torch.Tensor, dens: torch.Tensor, count: torch.Tensor, has_pts: torch.Tensor
) -> torch.Tensor:
    """Count error for every photo (relative, so 2 wrong out of 5 matters more than 2 out
    of 50), plus a map error where item positions are known."""
    total = pred.sum(dim=(1, 2, 3))
    count_loss = ((total - count) ** 2 / (count + 1.0)).mean()
    per_map = ((pred - dens) ** 2).sum(dim=(1, 2, 3))
    map_loss = (per_map * has_pts).sum() / has_pts.sum().clamp(min=1.0)
    return count_loss + 50.0 * map_loss


def evaluate(
    model: nn.Module, loader: torch.utils.data.DataLoader[Any]
) -> tuple[list[float], list[float]]:
    model.eval()
    preds: list[float] = []
    truth: list[float] = []
    with torch.no_grad():
        for x, _, c, _ in loader:
            preds += model(x).sum(dim=(1, 2, 3)).tolist()
            truth += c.tolist()
    return preds, truth


def metrics(preds: list[float], truth: list[float]) -> dict[str, float]:
    err = [abs(round(p) - t) for p, t in zip(preds, truth, strict=True)]
    return {
        "mae": round(sum(abs(p - t) for p, t in zip(preds, truth, strict=True)) / len(truth), 3),
        "exact": round(sum(e == 0 for e in err) / len(err), 3),
        "within_1": round(sum(e <= 1 for e in err) / len(err), 3),
        "within_10pct": round(
            sum(e <= max(1.0, 0.1 * t) for e, t in zip(err, truth, strict=True)) / len(err), 3
        ),
    }


def export_onnx(model: nn.Module, path: Path) -> float:
    """Write ONNX and return the largest difference between PyTorch and ONNX Runtime."""
    import onnxruntime as ort

    model.eval()
    x = torch.randn(2, 3, *INPUT_HW)
    torch.onnx.export(
        model,
        (x,),
        str(path),
        input_names=["image"],
        output_names=["density"],
        dynamic_axes={"image": {0: "n"}, "density": {0: "n"}},
        opset_version=17,
        dynamo=False,
    )
    with torch.no_grad():
        ref = model(x).numpy()
    got = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]).run(
        None, {"image": x.numpy()}
    )[0]
    return float(np.abs(ref - got).max())


def train(
    data: Path, out: Path, size: str = "tiny", pretrained: bool = False, epochs: int = 30,
    batch: int = 16, lr: float = 2e-3, seed: int = 0, label: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    random.seed(seed)
    torch.manual_seed(seed)
    samples = read_labels(data)
    if len(samples) < 20:
        raise SystemExit(f"need at least 20 labelled photos, have {len(samples)}")
    order = list(range(len(samples)))
    random.Random(seed).shuffle(order)
    n_val = max(3, int(len(samples) * 0.15))
    val = [samples[i] for i in order[:n_val]]
    tr = [samples[i] for i in order[n_val:]]
    loader = torch.utils.data.DataLoader(Photos(tr, True), batch_size=batch, shuffle=True)
    val_loader = torch.utils.data.DataLoader(Photos(val, False), batch_size=32)

    model = CountNet(size, pretrained)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * len(loader))
    best, best_state = math.inf, None
    for epoch in range(epochs):
        model.train()
        for x, d, c, h in loader:
            opt.zero_grad()
            loss_fn(model(x), d, c, h).backward()
            opt.step()
            sched.step()
        preds, truth = evaluate(model, val_loader)
        mae = metrics(preds, truth)["mae"]
        print(f"epoch {epoch + 1}/{epochs}: held-out mean absolute error {mae}", flush=True)
        if mae < best:
            best, best_state = mae, {k: v.clone() for k, v in model.state_dict().items()}
    assert best_state is not None
    model.load_state_dict(best_state)
    preds, truth = evaluate(model, val_loader)
    avg = sum(s.count for s in tr) / len(tr)
    report: dict[str, Any] = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data": label or "real",
        "network": size,
        "pretrained": pretrained,
        "photos": len(samples),
        "held_out": len(val),
        "with_points": sum(s.points is not None for s in samples),
        "model": metrics(preds, truth),
        "always_average": metrics([avg] * len(truth), truth),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    report["onnx_max_difference"] = export_onnx(model, out.with_suffix(".onnx"))
    meta = {
        "input_hw": list(INPUT_HW),
        "stride": STRIDE,
        "mean": list(MEAN),
        "std": list(STD),
        **report,
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="novaxis_ml.stock.train")
    ap.add_argument("--data", required=True, help="folder with photos and labels.jsonl")
    ap.add_argument("--out", required=True, help="output path without extension")
    ap.add_argument("--size", choices=["tiny", "mobilenet"], default="tiny")
    ap.add_argument("--pretrained", action="store_true")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--synthetic", action="store_true", help="label the model as synthetic")
    a = ap.parse_args(argv)
    report = train(
        Path(a.data), Path(a.out), a.size, a.pretrained, a.epochs,
        label="synthetic" if a.synthetic else "real",
    )  # fmt: skip
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
