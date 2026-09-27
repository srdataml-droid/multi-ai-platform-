"""Synthetic shelf photos with a known number of items, to prove the pipeline.

Not a substitute for real photos: the shapes, lighting and clutter are simple. It shows
that the network, training, export and serving all agree and that the network learns to
count before any real photo exists.

    uv run python -m novaxis_ml.stock.synthetic --out /tmp/shelves --n 2000
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 640, 480


def shelf_photo(rng: random.Random) -> tuple[Image.Image, list[tuple[float, float]]]:
    base = tuple(rng.randrange(150, 235) for _ in range(3))
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img)
    rows = rng.randint(2, 4)
    row_h = H / rows
    for r in range(1, rows):
        y = int(r * row_h)
        d.rectangle([0, y - 4, W, y + 4], fill=(90, 70, 50))
    kinds = [
        (tuple(rng.randrange(20, 230) for _ in range(3)), rng.choice(["can", "box"]))
        for _ in range(rng.randint(1, 3))
    ]
    points: list[tuple[float, float]] = []
    for r in range(rows):
        colour, kind = rng.choice(kinds)
        iw = rng.randint(34, 58)
        ih = int(iw * (1.6 if kind == "box" else 1.25))
        floor = int((r + 1) * row_h) - 6
        x = rng.randint(4, 30)
        while x + iw < W - 4:
            if rng.random() < 0.8:  # gaps where stock has sold
                top = floor - ih + rng.randint(-3, 3)
                box = [x, top, x + iw, floor]
                if kind == "can":
                    d.rounded_rectangle(box, radius=iw // 3, fill=colour, outline=(40, 40, 40))
                else:
                    d.rectangle(box, fill=colour, outline=(40, 40, 40))
                band = top + ih // 3
                d.rectangle([x + 3, band, x + iw - 3, band + ih // 5], fill=(245, 245, 245))
                points.append((x + iw / 2, top + ih / 2))
            x += iw + rng.randint(2, 12)
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0, 1.2)))
    light = rng.uniform(0.7, 1.2)
    img = img.point(lambda v: max(0, min(255, int(v * light))))
    return img, points


def write(folder: Path, n: int, seed: int = 11) -> None:
    rng = random.Random(seed)
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(n):
        img, pts = shelf_photo(rng)
        name = f"shelf_{i:05d}.jpg"
        img.save(folder / name, quality=88)
        lines.append(json.dumps({"image": name, "count": len(pts), "points": pts}))
    (folder / "labels.jsonl").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    write(Path(a.out), a.n, a.seed)
    print(f"wrote {a.n} photos to {a.out}")
