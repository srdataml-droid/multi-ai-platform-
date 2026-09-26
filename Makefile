.PHONY: up down test test-docker lint typecheck evals migrate seed demo web-install

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

migrate:       ## alembic upgrade head (Chunk 1)
	@echo "no migrations yet (Chunk 1)"

seed:          ## seed demo tenants (Chunk 1)
	@echo "no seed yet (Chunk 1)"

demo:          ## Chunk 0 demo: API answers, web shows it
	@echo "Open http://localhost:3000 after 'make up'. Expect: Reachable yes, Health ok."
	@curl -sf http://localhost:8000/health && echo && curl -sf http://localhost:8000/version && echo

web-install:
	cd apps/web && npm install --no-audit --no-fund
