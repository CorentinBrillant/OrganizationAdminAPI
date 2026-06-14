COMPOSE_LOCAL := docker compose --env-file .env.local -f docker-compose.local.yml
COMPOSE_PROD := docker compose --env-file .env.prod -f docker-compose.prod.yml

.PHONY: build up down restart logs ps clean test-backend test-frontend format-backend lint-frontend precommit-install scan-secrets up-prod down-prod logs-prod ps-prod

build-local:
	$(COMPOSE_LOCAL) build

up-local:
	$(COMPOSE_LOCAL) up --build

down-local:
	$(COMPOSE_LOCAL) down

restart-local: down-local up-local

logs-local:
	$(COMPOSE_LOCAL) logs -f

ps-local:
	$(COMPOSE_LOCAL) ps

up-prod:
	$(COMPOSE_PROD) up -d --build --remove-orphans

down-prod:
	$(COMPOSE_PROD) down

logs-prod:
	$(COMPOSE_PROD) logs -f

ps-prod:
	$(COMPOSE_PROD) ps

clean:
	$(COMPOSE) down -v --remove-orphans

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm run test:run

format-backend:
	cd backend && uv run ruff check --select F401 --fix .
	cd backend && uv run ruff format .

lint-frontend:
	cd frontend && if [ ! -x node_modules/.bin/biome ]; then npm ci; fi && npm run lint:frontend

precommit-install:
	uvx pre-commit install

scan-secrets:
	uvx pre-commit run gitleaks --all-files
