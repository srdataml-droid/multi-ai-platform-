"""Build identity reported by /version and by worker logs."""

from __future__ import annotations

import os

from novaxis_core import __version__


def build_info() -> dict[str, str]:
    """Version plus the git commit the image was built from, when known."""
    return {
        "version": __version__,
        "commit": os.environ.get("NOVAXIS_GIT_SHA", "dev"),
    }
