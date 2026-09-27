"""Photo preprocessing shared by stock-counter training (packages/ml) and serving
(stock_count.py): the network must see a photo the same way in both."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Network input (height, width): 3:4, like a phone photo. The density map is 1/8 of this.
INPUT_HW = (192, 256)
STRIDE = 8
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def load_image(
    data: bytes | Path,
    hw: tuple[int, int] = INPUT_HW,
    mean: tuple[float, ...] = MEAN,
    std: tuple[float, ...] = STD,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Photo -> normalised float32 array (3, H, W), and the upright photo's (width, height).
    Phone photos store rotation in EXIF; it is applied so the network sees what staff saw."""
    raw = Image.open(io.BytesIO(data) if isinstance(data, bytes) else data)
    img = ImageOps.exif_transpose(raw).convert("RGB")
    size = img.size
    img = img.resize((hw[1], hw[0]), Image.Resampling.BILINEAR)
    pixels = np.asarray(img, dtype=np.float32) / np.float32(255.0)
    m, s = np.asarray(mean, dtype=np.float32), np.asarray(std, dtype=np.float32)
    arr: np.ndarray = ((pixels - m) / s).astype(np.float32)
    return arr.transpose(2, 0, 1).copy(), size
