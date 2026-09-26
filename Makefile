.PHONY: up down test test-docker lint typecheck evals migrate migrate-new seed dev-token demo worker-once web-install

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

evals:         ## Golden-conversation evals (Chunk 5 onward)
	@echo "no evals yet; arrives with the first pack (Chunk 5)"

migrate:       ## alembic upgrade head
	uv run alembic -c packages/db/alembic.ini upgrade head

migrate-new:   ## autogenerate a migration: make migrate-new m="add foo"
	uv run alembic -c packages/db/alembic.ini revision --autogenerate -m "$(m)"

seed:          ## seed demo tenants (idempotent)
	uv run python -m novaxis_db.seed

dev-token:     ## mint a local JWT: make dev-token u=owner@demo-hvac
	uv run python -m novaxis_api.devtoken $(or $(u),owner@demo-hvac)

demo:          ## Chunk 3 demo: a web-chat message gets a worker reply
	@curl -sf http://localhost:8000/health >/dev/null || (echo "API not running: make up (or uv run uvicorn novaxis_api.main:app)"; exit 1)
	@R=$$(curl -s -X POST http://localhost:8000/inbound/webchat/demo-hvac -H 'Content-Type: application/json' \
	  -d '{"body":"Hi, my boiler is making a banging noise","name":"Demo Visitor"}'); echo "$$R"; \
	T=$$(echo "$$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["visitor_token"])'); \
	uv run python -m novaxis_worker.main --once; \
	curl -s "http://localhost:8000/inbound/webchat/demo-hvac/messages?visitor_token=$$T" | python3 -m json.tool

worker-once:   ## drain the job queue once and exit
	uv run python -m novaxis_worker.main --once

web-install:
	cd apps/web && npm install --no-audit --no-fund
