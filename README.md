# PlantFlow — SFG Transfer Tracking

PlantFlow is a prototype for tracking semi-finished-goods transfers and inventory across three plants.

## Architecture

- **Frontend:** React + TypeScript + Vite; target host Vercel.
- **API:** FastAPI; target host Render.
- **Database:** PostgreSQL; target provider Neon.
- **Local development:** Docker Compose with PostgreSQL.
- **Database schema:** versioned Alembic migrations.
- **Authentication:** JWT bearer tokens; Argon2 password hashing.
- **Authorization:** admin, manager and viewer roles, with plant-scoped inventory and transfer access.

## Current prototype features

- Create transfers with multiple SKU/quantity lines.
- Dispatch and receive actions record server-generated UTC timestamps.
- Dispatch moves stock from source on-hand to source in-transit; receipt moves accepted units into destination stock.
- Partial receipts, discrepancy notes, event history and stock movement records.
- Search by transfer number or SKU; filter by status and date range.
- Dashboard metrics and CSV export.
- Three demo plants and sample SKUs are seeded into an empty database.
- Admins can provision accounts through the protected `POST /api/users` endpoint.

## Run locally on Windows 11

1. Install Docker Desktop.
2. Copy `.env.example` to `.env`.
3. Replace the example JWT secret, admin email and admin password in `.env`. Use a unique password with at least 12 characters.
4. From the repository root run:

```powershell
docker compose up --build
```

Open:
- UI: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

Sign in using the bootstrap admin email and password from your local `.env`. Do not use the example values in a hosted environment.

Stop with `Ctrl+C`; run `docker compose down` to stop containers. To reset the local database and demo accounts, run `docker compose down -v`.

## Roles

| Role | Access |
|---|---|
| Admin | All plants, all transfers, user provisioning |
| Manager | Create/dispatch transfers from assigned plant; receive transfers into assigned plant |
| Viewer | Read-only access scoped to assigned plant |

Create a manager or viewer account as an administrator:

```powershell
$token = "ADMIN_ACCESS_TOKEN"
$body = @{ email="manager@example.com"; password="Use-A-Unique-Password"; role="manager"; plant_id=1 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/users" -Headers @{ Authorization="Bearer $token" } -ContentType "application/json" -Body $body
```

The API returns a bearer token from `POST /api/auth/login`. Access tokens expire after the configured `TOKEN_MINUTES` (default 480 minutes). The current UI supports login and sign-out; account provisioning is through the protected API.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Render, Vercel and Neon configuration. Never commit `.env`, database URLs, passwords, JWT secrets or SAP credentials.

## Future integrations

SAP S/4HANA, GPS/carrier feeds and an AI assistant are not connected. SAP edition, APIs, authentication, connectivity and data ownership must be confirmed with Indus before implementing the connector.

## Production readiness limitations

This remains a prototype. Before live plant use, complete a security review, TLS/domain configuration, backup and restore drills, audit retention, monitoring/alerting, rate limiting, password reset and account recovery, session revocation, formal concurrency testing, and business acceptance testing. The manager/viewer authorization is plant-scoped for inventory and transfer operations, but the product catalogue and plant directory are shared reference data. A dedicated user administration UI is not yet included.
