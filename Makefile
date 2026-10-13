# EduCenter Telegram CRM - common commands. Run `make help`.
SHELL := /bin/bash
COMPOSE := docker compose
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- Docker (production)
.PHONY: up down build logs ps migrate superadmin tg-login tg-logout backup restore
up: ## Build and start the whole stack
	$(COMPOSE) up -d --build

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) down

build: ## Build images
	$(COMPOSE) build

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=100

ps: ## Service status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate

superadmin: ## Create the first Super Admin (asks for the password)
	@read -p "Login: " u; $(COMPOSE) run --rm api python -m app.cli create-superadmin --username "$$u"

tg-login: ## One-time Telegram login (stops the worker while running)
	$(COMPOSE) stop worker
	$(COMPOSE) run --rm worker python -m app.telegram.auth_cli
	$(COMPOSE) start worker

tg-logout: ## Terminate the Telegram session and delete it
	$(COMPOSE) stop worker
	$(COMPOSE) run --rm worker python -m app.telegram.auth_cli --logout

backup: ## Dump the database to ./backups
	./scripts/backup.sh

restore: ## Restore a dump: make restore FILE=backups/xxx.sql.gz
	./scripts/restore.sh "$(FILE)"

# ---------------------------------------------------------------- Local development
.PHONY: dev-install dev-api dev-worker dev-web test lint format typecheck check
dev-install: ## Create venv and install backend + frontend dependencies
	python3 -m venv $(VENV)
	$(PY) -m pip install -e "backend[dev]"
	cd frontend && npm ci

dev-api: ## Run the API with auto-reload (needs DATABASE_URL)
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

dev-worker: ## Run the Telegram worker locally
	cd backend && ../$(PY) -m app.workers.main

dev-web: ## Run the Vite dev server (proxies /api to :8000)
	cd frontend && npm run dev

test: ## Run backend tests (needs TEST_DATABASE_URL pointing to an empty test database)
	cd backend && ../$(PY) -m pytest -q

lint: ## Lint backend
	cd backend && ../$(VENV)/bin/ruff check app tests && ../$(VENV)/bin/ruff format --check app tests

format: ## Format backend code
	cd backend && ../$(VENV)/bin/ruff format app tests && ../$(VENV)/bin/ruff check --fix app tests

typecheck: ## Type-check and build the frontend
	cd frontend && npm run build

check: lint test typecheck ## Everything CI should run
