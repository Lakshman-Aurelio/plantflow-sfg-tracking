# Architecture

- Frontend: React + TypeScript + Vite single-page application consuming JSON REST endpoints.
- Backend: FastAPI; business actions and stock validation run server-side.
- Persistence: SQLite for local demo. Relational tables hold plants, products, inventory, transfers, transfer lines, events and stock movements. Move to PostgreSQL plus migrations before multi-user deployment.
- Auditability: transfer events preserve lifecycle history; stock movements record dispatch/receipt effects.

## Scaling path
1. Replace demo plant/product data with ERP master data.
2. Move to PostgreSQL, add migrations, transaction isolation and backups.
3. Add authentication, plant-scoped role access, approvals and audit retention.
4. Add idempotency keys, an outbox/event queue and observability.
5. Add pagination and indexed search for large histories.