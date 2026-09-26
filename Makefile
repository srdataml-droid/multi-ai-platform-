.PHONY: up down test test-docker lint typecheck evals evals-real migrate migrate-new seed dev-token demo worker-once web-install

up:            ## Start postgres, api, worker, web
	docker compose up --build

down:
	docker compose down

test:          ## Python tests plus web unit tests
	uv run pytest -q
	cd apps/web && node --test --experimental-strip-types app/*.test.ts

test-docker:   ## Python tests inside the container image
	docker compose --profile test run --rm test

lint:          ## ruff + eslint
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && npm run lint

typecheck:     ## mypy strict on core + tsc on web
	uv run mypy
	cd apps/web && npm run typecheck

evals:         ## Golden-conversation evals with the scripted model (deterministic)
	uv run python evals/run.py

evals-real:    ## Same evals against the real model (needs ANTHROPIC_API_KEY)
	uv run python evals/run.py --real

migrate:       ## alembic upgrade head
	uv run alembic -c packages/db/alembic.ini upgrade head

migrate-new:   ## autogenerate a migration: make migrate-new m="add foo"
	uv run alembic -c packages/db/alembic.ini revision --autogenerate -m "$(m)"

seed:          ## seed demo tenants (idempotent)
	uv run python -m novaxis_db.seed

dev-token:     ## mint a local JWT: make dev-token u=owner@demo-hvac
	uv run python -m novaxis_api.devtoken $(or $(u),owner@demo-hvac)

demo:          ## Chunk 6 demo: dental evals; a symptom is encrypted at rest and redacted for a viewer
	uv run python evals/run.py --pack dental
	@echo "--- raw row: symptom is stored as enc:v1:... ---"
	@psql "$$(echo "$${NOVAXIS_DATABASE_URL:-postgresql://novaxis:novaxis@localhost:5432/novaxis}" | sed 's/+psycopg//')" -tAc "select extracted->>'symptom' from conversations where extracted ? 'symptom' order by created_at desc limit 1" | cut -c1-40

worker-once:   ## drain the job queue once and exit
	uv run python -m novaxis_worker.main --once

web-install:
	cd apps/web && npm install --no-audit --no-fund
