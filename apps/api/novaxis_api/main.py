"""The API process.

Why it is thin: an inbound webhook must be acknowledged in well under a second
or the provider retries. So this process stores and enqueues, and the worker
process does everything slow.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from starlette.concurrency import run_in_threadpool

from novaxis_api.routes_alerts import router as alerts_router
from novaxis_api.routes_appointments import router as appointments_router
from novaxis_api.routes_approvals import router as approvals_router
from novaxis_api.routes_auth import router as auth_router
from novaxis_api.routes_billing import router as billing_router
from novaxis_api.routes_bridge import router as bridge_router
from novaxis_api.routes_conversations import router as conversations_router
from novaxis_api.routes_dashboard import router as dashboard_router
from novaxis_api.routes_inbound import router as inbound_router
from novaxis_api.routes_integrations import router as integrations_router
from novaxis_api.routes_internal import router as internal_router
from novaxis_api.routes_me import router as me_router
from novaxis_api.routes_media import router as media_router
from novaxis_api.routes_onboarding import router as onboarding_router
from novaxis_api.routes_operator import router as operator_router
from novaxis_api.routes_settings import router as settings_router
from novaxis_api.routes_signup import router as signup_router
from novaxis_core.settings import get_settings
from novaxis_core.version import build_info

WIDGET_PREFIX = "/inbound/webchat/"


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
    app.include_router(alerts_router)
    app.include_router(inbound_router)
    app.include_router(approvals_router)
    app.include_router(conversations_router)
    app.include_router(media_router)
    app.include_router(bridge_router)
    app.include_router(integrations_router)
    app.include_router(appointments_router)
    app.include_router(dashboard_router)
    app.include_router(settings_router)
    app.include_router(auth_router)
    app.include_router(internal_router)
    app.include_router(signup_router)
    app.include_router(onboarding_router)
    app.include_router(billing_router)
    app.include_router(operator_router)

    @app.middleware("http")
    async def widget_cors(request: Request, call_next):  # type: ignore[no-untyped-def]
        # The chat widget runs on each business's own website and calls these routes from
        # that origin. They carry no cookies and no staff token, so any origin may call them;
        # per-tenant origin allow-lists come with Chunk 12. Every other route stays
        # same-origin only (the dashboard reaches the API through the web app's /api proxy).
        if not request.url.path.startswith(WIDGET_PREFIX):
            return await call_next(request)
        if request.method == "OPTIONS":
            response: Response = Response(status_code=204)
        else:
            response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "content-type"
        response.headers["Access-Control-Max-Age"] = "600"
        return response

    if get_settings().inline_worker:
        from novaxis_api.inline_worker import drain_for

        @app.middleware("http")
        async def run_jobs_after_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
            response: Response = await call_next(request)
            # Serverless has no worker process: do the queued work before replying.
            if request.method in ("POST", "PUT") and not request.url.path.startswith("/internal"):
                await run_in_threadpool(drain_for)
            return response

    return app


app = create_app()
