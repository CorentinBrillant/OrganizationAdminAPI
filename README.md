# OrganizationAdminAPI

The goal of this api is to help the administration of an organization.

## Run with Docker Compose

From the project root:

```bash
cp .env.local.example .env.local
docker compose --env-file .env.local -f docker-compose.local.yml up --build
```

Services:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

The frontend proxies `/api/*` requests to the backend container.

## Production deployment

The production stack uses `docker-compose.prod.yml` and `.env.prod`.
In production, a dedicated Nginx service serves the frontend static files and proxies `/api/*` to the Gunicorn backend.

From the project root:

```bash
make up-prod
```

Useful related commands:

```bash
make ps-prod
make logs-prod
make down-prod
```

## Secret scanning on commit

This repository uses `pre-commit` with `gitleaks` to detect potential secrets before a commit is created.

From the project root:

```bash
make precommit-install
```

To run the secret scan manually on all tracked files:

```bash
make scan-secrets
```

## Environment variables

Use root env files:

- Local development: `.env.local`
- Production deployment: `.env.prod`
- Backend reads values through Docker Compose `env_file`.
- Frontend receives only explicitly mapped variables (for now: `VITE_API_AUTH_TOKEN`).
- If you run the frontend outside Docker (`cd frontend && npm run dev`), Vite is configured to read env files from the repository root.
