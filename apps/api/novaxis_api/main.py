"""The API process.

Why it is thin: an inbound webhook must be acknowledged in well under a second
or the provider retries. So this process stores and enqueues, and the worker
process does everything slow.
"""

from __future__ import annotations

from fastapi import FastAPI

from novaxis_api.routes_appointments import router as appointments_router
from novaxis_api.routes_approvals import router as approvals_router
from novaxis_api.routes_conversations import router as conversations_router
from novaxis_api.routes_inbound import router as inbound_router
from novaxis_api.routes_integrations import router as integrations_router
from novaxis_api.routes_me import router as me_router
from novaxis_api.routes_media import router as media_router
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

    app.include_router(me_router)
    app.include_router(inbound_router)
    app.include_router(approvals_router)
    app.include_router(conversations_router)
    app.include_router(media_router)
    app.include_router(integrations_router)
    app.include_router(appointments_router)
    return app


app = create_app()
