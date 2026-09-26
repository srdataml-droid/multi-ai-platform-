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

demo:          ## Chunk 7 demo: restoration evals; an email with a photo lands stored under the tenant prefix
	uv run python evals/run.py --pack restoration
	@curl -sf http://localhost:8000/health >/dev/null || (echo "API not running, skipping live photo"; exit 0)
	@PNG=$$(python3 -c 'import base64;print(base64.b64encode(b"\x89PNG\r\n\x1a\n"+b"\0"*64).decode())'); \
	curl -s -X POST "http://localhost:8000/inbound/email/postmark?token=$${NOVAXIS_POSTMARK_INBOUND_TOKEN:-demo}" -H 'Content-Type: application/json' \
	  -d "{\"MessageID\":\"pm-demo-$$RANDOM\",\"FromFull\":{\"Email\":\"owner@example.com\",\"Name\":\"Demo Owner\"},\"ToFull\":[{\"Email\":\"demo-restoration@inbound.novaxis.test\"}],\"Subject\":\"Burst pipe\",\"StrippedTextReply\":\"Pipe burst last night, stopped now, photo attached\",\"Attachments\":[{\"Name\":\"kitchen.png\",\"ContentType\":\"image/png\",\"Content\":\"$$PNG\"}]}"; echo; \
	ls -R "$${NOVAXIS_STORAGE_LOCAL_DIR:-.novaxis-media}" | tail -4

worker-once:   ## drain the job queue once and exit
	uv run python -m novaxis_worker.main --once

web-install:
	cd apps/web && npm install --no-audit --no-fund
