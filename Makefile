.PHONY: up down test test-docker lint typecheck evals evals-real e2e migrate migrate-new seed dev-token demo worker-once web-install ml-train-synthetic ml-train ml-export ml-train-approvals-synthetic ml-train-approvals ml-export-approvals

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

evals-real:    ## Same evals against the configured real model (NOVAXIS_LLM_PROVIDER, see docs/models.md)
	uv run python evals/run.py --real

migrate:       ## alembic upgrade head
	uv run alembic -c packages/db/alembic.ini upgrade head

migrate-new:   ## autogenerate a migration: make migrate-new m="add foo"
	uv run alembic -c packages/db/alembic.ini revision --autogenerate -m "$(m)"

seed:          ## seed demo tenants (idempotent)
	uv run python -m novaxis_db.seed

dev-token:     ## mint a local JWT: make dev-token u=owner@demo-hvac
	uv run python -m novaxis_api.devtoken $(or $(u),owner@demo-hvac)

demo:          ## Chunk 9 demo: the pilot demo in the browser. API + web must be running; then open http://localhost:3000
	@curl -sf http://localhost:8000/health >/dev/null || (echo "API not running: uv run uvicorn novaxis_api.main:app"; exit 1)
	@echo "1. Open http://localhost:3000 and sign in as owner@demo-hvac.test (local mode, no password)."
	@echo "2. In another tab open the widget test page: http://localhost:3000/widget-demo.html and send a message."
	@echo "3. Run 'make worker-once' (or leave 'novaxis-worker' running), then approve in the dashboard."
	uv run python tools/demo_scheduling.py

e2e:           ## Playwright pilot test (API must be running with NOVAXIS_LLM_PROVIDER=fake)
	cd apps/web && NOVAXIS_REPO_ROOT=$(CURDIR) npx playwright test

worker-once:   ## drain the job queue once and exit
	uv run python -m novaxis_worker.main --once

web-install:
	cd apps/web && npm install --no-audit --no-fund

ml-train-synthetic: ## No-show model on synthetic data: proves the pipeline (docs/ml.md)
	uv run python -m novaxis_ml.no_show train --source synthetic

ml-train:      ## No-show model on real recorded outcomes (reads the database)
	uv run python -m novaxis_ml.no_show train --source db

ml-export:     ## Training table as CSV for notebooks
	uv run python -m novaxis_ml.no_show export --out ml-rows.csv

ml-train-approvals-synthetic: ## Approval model on synthetic decisions (docs/ml.md section 8)
	uv run python -m novaxis_ml.approvals train --source synthetic

ml-train-approvals: ## Approval model on real staff decisions (reads the database)
	uv run python -m novaxis_ml.approvals train --source db

ml-export-approvals: ## Approval training table as CSV
	uv run python -m novaxis_ml.approvals export --out approval-rows.csv
