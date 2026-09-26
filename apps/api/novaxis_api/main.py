"""The API process.

Why it is thin: an inbound webhook must be acknowledged in well under a second
or the provider retries. So this process stores and enqueues, and the worker
process does everything slow.
"""

from __future__ import annotations

from fastapi import FastAPI

from novaxis_core.settings import get_settings
from novaxis_core.version import build_info


def create_app() -> FastAPI:
    """Build the app. A factory so tests can build fresh instances."""
    app = FastAPI(title="Novaxis AI Worker API", version=build_info()["version"])

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "env": get_settings().env}

    @app.get("/version")
    def version() -> dict[str, str]:
        return build_info()

    return app


app = create_app()
