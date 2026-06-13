COMPOSE := docker compose --env-file .env.local

.PHONY: build up down restart logs ps clean test-backend test-frontend format-backend lint-frontend

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

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
	cd frontend && npm run lint:frontend
