# Architecture

## Runtime topology

- **Frontend:** React + TypeScript + Vite; deployed as a Vercel static site.
- **API:** FastAPI; deployed as a Render web service.
- **Database:** PostgreSQL; Neon is the target managed provider.
- **Local environment:** Docker Compose runs PostgreSQL, API and Vite UI.
- **Persistence:** PostgreSQL tables hold plants, products, inventory, transfers, transfer lines, events and stock movements. The API uses psycopg and parameterized SQL.
- **Database initialization:** a version marker records the initial schema migration. Schema changes must be delivered as reviewed, versioned migrations; do not make ad-hoc production schema edits.

## Boundaries

Transfer lifecycle and stock validation remain in the PlantFlow API. ERP connectivity belongs behind the ERP adapter interface in `backend/app/integrations`; an SAP-specific connector must not be called directly from transfer routes. This keeps the transfer workflow independent of the ERP vendor.

## Scale and production hardening still required

1. Add authentication, role-based access and plant-scoped authorization.
2. Add idempotency keys for dispatch/receipt and robust concurrency tests.
3. Introduce a durable outbox and background workers for ERP synchronization, retries and reconciliation.
4. Add pagination, query plans and indexes based on real data volumes.
5. Add structured logs, metrics, alerts, backups, restore drills and audit retention.
6. Review isolation levels, locking, deadlock handling and operational failure modes.
7. Add a formal Alembic migration workflow before evolving the schema beyond the initial version.

## SAP S/4HANA readiness

The ERP adapter is an architectural seam, not a live integration. SAP S/4HANA is a candidate target based on the placement-talk reference, but Indus must confirm its actual SAP product/edition, deployment model, released APIs, authentication, connectivity and material/plant/storage-location mappings before implementation.
