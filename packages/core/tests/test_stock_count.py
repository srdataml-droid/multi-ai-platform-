"""Serving the stock counter: the shipped network counts synthetic shelves it never saw,
shows where it counted, and a synthetic network stays with demo businesses."""

from __future__ import annotations

import io
import random

from PIL import Image

from novaxis_core import stock_count
from novaxis_core.vision import INPUT_HW, load_image


def _shelf(seed: int) -> tuple[bytes, int]:
    from novaxis_ml.stock.synthetic import shelf_photo

    img, points = shelf_photo(random.Random(seed))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), len(points)


def test_the_shipped_counter_counts_unseen_shelves_within_one_or_two() -> None:
    stock_count.load.cache_clear()
    c = stock_count.load()
    assert c is not None and c.synthetic
    errors = []
    for seed in range(1000, 1012):  # seeds the training set never used
        photo, truth = _shelf(seed)
        r = c.count(photo)
        errors.append(abs(r.count - truth))
        assert abs(len(r.points) - truth) <= max(3, truth * 0.2), "dots show what was counted"
        assert all(0 <= x <= 640 and 0 <= y <= 480 for x, y in r.points)
    assert sum(errors) / len(errors) <= 1.5 and max(errors) <= 4


def test_an_empty_shelf_counts_zero_and_any_photo_size_works() -> None:
    c = stock_count.load()
    assert c is not None
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (200, 190, 170)).save(buf, format="PNG")
    assert c.count(buf.getvalue()).count == 0
    arr, size = load_image(buf.getvalue())
    assert arr.shape == (3, *INPUT_HW) and size == (1200, 900)


def test_a_synthetic_counter_is_only_used_for_demo_businesses() -> None:
    assert stock_count.counter_for("demo-hvac") is not None
    assert stock_count.counter_for("corner-shop") is None
