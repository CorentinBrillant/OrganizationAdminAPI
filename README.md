# OrganizationAdminAPI

The goal of this api is to help the administration of an organization.

## Run with Docker Compose

From the project root:

```bash
docker compose up --build
```

Services:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

The frontend proxies `/api/*` requests to the backend container.
