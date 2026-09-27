.PHONY: install dev dev-mock test test-sql test-frontend lint docker-build

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

dev:
	APP_ENV=development AUTH_MODE=supabase HARNESS_PROVIDER=mock APP_PUBLIC_URL=http://127.0.0.1:8080 .venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8080 $(if $(wildcard .env.local),--env-file .env.local)

dev-mock:
	APP_ENV=development AUTH_MODE=none HARNESS_PROVIDER=mock .venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8080

test:
	.venv/bin/pytest -q

test-sql:
	RUN_SQL_TESTS=1 .venv/bin/pytest -q backend/tests/test_membership_sql.py

test-frontend:
	node --test backend/tests/frontend_state.test.mjs

lint:
	.venv/bin/ruff check backend

docker-build:
	docker build -t brain-alpha-harness:local .
