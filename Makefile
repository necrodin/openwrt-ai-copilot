PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

PY_PACKAGES := ./database ./ai ./providers ./rag ./vision ./vectorstore ./router-agent ./backend

.PHONY: install dev-backend dev-frontend test lint format docker-up docker-down clean

## Bootstrap: create venv, install python packages + npm dependencies
install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	@for pkg in $(PY_PACKAGES); do $(PIP) install -e $$pkg || exit 1; done
	cd frontend && npm install

## Run FastAPI backend on :8000 with auto-reload
dev-backend:
	$(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Run Next.js frontend on :3000
dev-frontend:
	cd frontend && npm run dev

## Run the test suite (pytest)
test:
	$(PY) -m pytest

## Lint + format check (ruff)
lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

## Auto-format (ruff)
format:
	$(PY) -m ruff format .

## Build and start the full stack in Docker
docker-up:
	docker compose -f docker/docker-compose.yml up --build -d

## Stop the Docker stack
docker-down:
	docker compose -f docker/docker-compose.yml down

## Remove venv, node_modules, build artifacts, and local data
clean:
	rm -rf $(VENV) frontend/node_modules frontend/.next frontend/out data
