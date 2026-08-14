.PHONY: dev dev-down dev-logs migrate seed test test-api test-web lint lint-api lint-web typecheck types build down

dev:
	docker compose up --build -d

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m infra.scripts.seed

test-api:
	docker compose exec -e APP_ENV=test \
		-e TEST_DATABASE_URL=postgresql+asyncpg://marketingos:marketingos_dev@postgres:5432/marketingos_test \
		-e TEST_REDIS_URL=redis://redis:6379/15 \
		api pytest tests/ -v

test-web:
	docker compose exec web npm run test

test:
	$(MAKE) test-api

lint-api:
	docker compose exec api ruff check src tests

lint-web:
	docker compose exec web npm run lint

lint:
	$(MAKE) lint-api
	$(MAKE) lint-web

typecheck:
	docker compose exec web npm run typecheck

types:
	infra/scripts/generate-types.sh

build:
	docker compose build