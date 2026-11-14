# PlantFlow — SFG Transfer Tracking

PlantFlow is a prototype for tracking semi-finished-goods transfers and inventory across three plants, with traceability to parent-build job orders.

## Architecture

- **Frontend:** React + TypeScript + Vite; target host Vercel.
- **API:** FastAPI; target host Render.
- **Database:** PostgreSQL; target provider Neon.
- **Local development:** Docker Compose with PostgreSQL.
- **Schema:** versioned Alembic migrations.
- **Authentication:** JWT bearer tokens; Argon2 password hashing.
- **Authorization:** admin, manager and viewer roles, with plant-scoped inventory and transfer access.

## Prototype features

- Create transfers with multiple SKU/quantity lines and optional parent-build job order reference.
- Import a sample job order JSON file from the **Job Orders** screen.
- Keep the parent build reference visible in transfer details.
- Dispatch and receive actions record server-generated UTC timestamps.
- Dispatch moves stock from source on-hand to source in-transit; receipt moves accepted units into destination stock.
- Partial receipts, discrepancy notes, event history and stock movement records.
- Search by transfer number or SKU; filter by status and date range.
- Dashboard metrics and CSV export.
- Three demo plants and sample SKUs are seeded into an empty database.

## Job order system demonstration

The existing job order system remains the system of record for parent builds. The sample contract is [job-order-JO-2026-001.json](docs/samples/job-order-JO-2026-001.json). The API accepts the JSON payload at `POST /api/job-orders/import`; imported orders can be listed and linked to SFG transfers. The Job Orders screen imports the committed sample file. This is a simulated interface contract: no real external system is connected and PlantFlow does not send updates back. See [integration details](docs/JOB_ORDER_INTEGRATION.md).

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

Sign in using the bootstrap admin email and password from your local `.env`.

## Deployment and limitations

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Render, Vercel and Neon configuration and [docs/DELIVERY_NOTE.md](docs/DELIVERY_NOTE.md) for assumptions, design decisions and next steps.

This remains a prototype. Real job-order integration, SAP S/4HANA, GPS/carrier feeds and AI are not connected. Production use requires confirmed master data, agreed interfaces, security review, backups, monitoring, concurrency/idempotency testing and business acceptance.
