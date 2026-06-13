# OrganizationAdminAPI

The goal of this api is to help the administration of an organization.

## Run with Docker Compose

From the project root:

```bash
cp .env.local.example .env.local
docker compose --env-file .env.local up --build
```

Services:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

The frontend proxies `/api/*` requests to the backend container.

## Environment variables

Use a single root file: `.env.local`.

- Backend reads values through Docker Compose `env_file`.
- Frontend receives only explicitly mapped variables (for now: `VITE_API_AUTH_TOKEN`).
- If you run the frontend outside Docker (`cd frontend && npm run dev`), Vite is configured to read env files from the repository root.
