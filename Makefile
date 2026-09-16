.PHONY: install dev test lint docker-build

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

dev:
	APP_ENV=development HARNESS_PROVIDER=mock .venv/bin/uvicorn backend.app.main:app --reload --port 8080

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check backend

docker-build:
	docker build -t brain-alpha-harness:local .

