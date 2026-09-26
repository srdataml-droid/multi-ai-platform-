# One image for api and worker; the start command differs per service.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/
WORKDIR /app

# Install dependencies first so source edits do not bust the layer cache.
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/packs/pyproject.toml packages/packs/pyproject.toml
COPY packages/db/pyproject.toml packages/db/pyproject.toml
RUN uv sync --all-packages --no-dev --frozen --no-install-workspace

COPY apps ./apps
COPY packages ./packages
COPY evals ./evals
RUN uv sync --all-packages --no-dev --frozen

ARG GIT_SHA=dev
ENV NOVAXIS_GIT_SHA=$GIT_SHA PATH="/app/.venv/bin:$PATH"

# Default is the API; compose and the platform override for the worker.
CMD ["uvicorn", "novaxis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
