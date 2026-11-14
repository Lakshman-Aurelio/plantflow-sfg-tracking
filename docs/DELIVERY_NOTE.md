# PlantFlow — delivery note

## Assumptions
- Three plants exchange semi-finished goods during a parent build.
- The sender records dispatch and the receiving plant records actual receipt.
- Demo plants, SKUs and job orders are illustrative because production master data was not supplied.
- The existing job order system remains authoritative for parent-build orders; PlantFlow records SFG movement against a supplied job-order reference.

## Key design decisions and trade-offs
- A browser-based React frontend and FastAPI API provide a simple demonstrable workflow.
- PostgreSQL persistence and versioned Alembic migrations are used so the prototype can move from local Docker Compose to managed hosting.
- Dispatch and receipt are separate recorded actions with timestamps, quantity validation and an event/stock movement trail.
- A JSON job-order contract demonstrates how the existing system could send parent-build data without connecting to a real system.
- SAP is kept behind a vendor-neutral ERP adapter boundary; no SAP calls or credentials are required.

## What I would build next
- Confirm real plant, warehouse, SKU and job-order master data with the business.
- Complete production deployment, security review, backups, monitoring and concurrency/idempotency testing.
- Agree the actual job-order interface and implement authenticated, retryable synchronization and reconciliation.
- Confirm Indus's SAP product/edition and released APIs before implementing an SAP connector.
