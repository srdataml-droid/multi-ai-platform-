# ADR 0001: Stack and repo shape

- Status: accepted
- Date: 2026-09-26
- Chunk: 0

## Context
The founder builds alone, alongside a full-time job, on a laptop with no GPU. The stack must be
one they already deploy with, and the repo must let one Claude Code session own one chunk
without touching the rest.

## Decision
- Python 3.12 monorepo managed by `uv` workspaces: `apps/api` (FastAPI), `apps/worker`,
  `packages/core`, `packages/packs`, `packages/db`. Each is its own package so imports
  declare dependencies explicitly and `packages/core` can never import an app.
- One Docker image for api and worker, different start commands.
- `apps/web` is a Next.js App Router app, kept outside the Python workspace with its own
  `package.json`. In dev it rewrites `/api/*` to the FastAPI process so the browser never
  needs CORS configuration.
- Tailwind and shadcn/ui are deferred to Chunk 9. Chunk 0 ships one unstyled page.
- Tests: pytest for Python, Node's built-in test runner for the web's non-React logic
  (no Jest or Vitest until a React component needs testing, in Chunk 9).
- Lint and types: ruff and mypy strict (scoped to `packages/core` until the other packages
  have real code), eslint and tsc.
- CI: GitHub Actions, two jobs (python, web), on every push and pull request.

## Alternatives considered
- Poetry or pip-tools: `uv` workspaces are faster and handle the multi-package layout natively.
- Redis-backed queue: rejected for Phase 1, see ADR 0002 when written (Chunk 3).
- Single Python package: rejected because pack code would be able to import core internals
  and apps would drift into each other.
- Vitest for the web now: rejected as a dependency with no consumer yet.

## Consequences
- Adding a package means adding it to the workspace members list and to the Dockerfile's
  dependency-layer copy list. Two places, both in the root.
- The web build uses `output: standalone` so the production image is small; the
  `apps/web/Dockerfile` depends on that setting.
