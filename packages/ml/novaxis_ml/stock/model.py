"""The counting network: a photo in, a density map out; the count is the map's sum.

Two sizes:
- `tiny` (about 100k weights): trains from scratch on a CPU in minutes. Used for the
  synthetic proof and as a small, fast default.
- `mobilenet`: MobileNetV3-small's first layers, pretrained on ImageNet, with the same
  counting head. Use it for real photos: a network that already knows edges and shapes
  needs far fewer labelled photos. The pretrained weights download on first use (Colab or
  your laptop; not in this repo).
"""

from __future__ import annotations

import torch
from torch import nn


def _block(cin: int, cout: int, dilation: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=dilation, dilation=dilation, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class Head(nn.Module):
    """Context (dilated convolutions) then a 1x1 convolution to a non-negative density."""

    def __init__(self, cin: int) -> None:
        super().__init__()
        self.body = nn.Sequential(_block(cin, 64, 2), _block(64, 32, 2))
        self.out = nn.Conv2d(32, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.relu(self.out(self.body(x)))


class CountNet(nn.Module):
    def __init__(self, size: str = "tiny", pretrained: bool = False) -> None:
        super().__init__()
        self.size = size
        if size == "tiny":
            self.features = nn.Sequential(
                _block(3, 16), _block(16, 16), nn.MaxPool2d(2),
                _block(16, 32), _block(32, 32), nn.MaxPool2d(2),
                _block(32, 64), _block(64, 64), nn.MaxPool2d(2),
            )  # fmt: skip
            channels = 64
        elif size == "mobilenet":
            from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

            weights = MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
            # The first four stages bring the image to 1/8 size with 24 channels.
            self.features = mobilenet_v3_small(weights=weights).features[:4]
            channels = 24
        else:
            raise ValueError(f"unknown network size {size!r}")
        self.head = Head(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))  # (N, 1, H/8, W/8)
