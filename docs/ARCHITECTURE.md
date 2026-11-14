# Architecture

## Runtime topology

- **Frontend:** React + TypeScript + Vite; target host Vercel.
- **API:** FastAPI; target host Render.
- **Database:** PostgreSQL; Neon is the target managed provider.
- **Local environment:** Docker Compose runs PostgreSQL, API and Vite UI.
- **Persistence:** PostgreSQL stores plants, products, inventory, transfers, transfer lines, events, stock movements, users and imported parent-build job orders.
- **Schema:** versioned Alembic migrations; the API uses psycopg and parameterized SQL.

## Job order system boundary

The existing job order system remains authoritative for the parent build. PlantFlow accepts a documented JSON job-order contract through `POST /api/job-orders/import`, stores the original payload and an import event, and exposes imported orders through read endpoints. SFG transfers can reference an imported `job_order_id`; transfer details show the parent-build reference. A representative payload is committed at `docs/samples/job-order-JO-2026-001.json` and copied to the frontend sample-import screen.

This is a demonstrable interface contract, not a live connection. No message is sent back to the external job-order system. See [Job Order Integration](JOB_ORDER_INTEGRATION.md).

## ERP / SAP boundary

Transfer lifecycle and stock validation remain in the PlantFlow API. ERP connectivity belongs behind the vendor-neutral adapter interface in `backend/app/integrations`; the SAP S/4HANA connector is a placeholder and is not called by transfer routes. Indus must confirm its SAP product/edition, deployment model, released APIs, authentication, connectivity and plant/material/storage-location mappings before implementation.

## Scale and production hardening still required

1. Add idempotency keys and durable outbox/background workers for external synchronization and reconciliation.
2. Add pagination and query-plan tuning based on real data volumes.
3. Add structured logs, metrics, alerts, backups, restore drills and audit retention.
4. Review isolation levels, locking, deadlock handling and operational failure modes.
5. Complete security review, rate limiting, password recovery, token revocation and monitoring.
