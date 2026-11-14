# PlantFlow — delivery note

## Assumptions
- The three plants, SKUs and quantities in the prototype are illustrative because production master data was not supplied.
- The sending plant records dispatch; the receiving plant records actual accepted quantities. PlantFlow records the movement trail and prototype inventory ledger.
- The production SAP product/edition, supported interface and integration mechanism were not specified. The design therefore assumes a vendor-neutral API boundary so a future SAP-specific adapter can map the confirmed interface. No SAP connector, SAP configuration or live SAP exchange is implemented.
- The real job-order JSON schema was not supplied. The prototype defines an illustrative contract in `docs/samples/job-order-JO-2026-001.json`: `job_order_id`, `parent_build`, `product`, `quantity`, `unit`, and `required_sfg` (an array of `sku` and `quantity`). The API validates and stores the payload; transfers can reference the imported `job_order_id`. These field names and structures are assumptions to be mapped to the actual source schema.

## Key design decisions and trade-offs
- React + TypeScript provides the browser UI; FastAPI exposes the application API; PostgreSQL stores persistent records; Docker Compose provides reproducible local execution.
- Transfers use explicit Draft, In Transit, Partially Received and Received states. Dispatch/receipt events, accepted quantities and discrepancy notes create a checkable movement trail.
- The relational database and API are straightforward to inspect and extend, but production scalability and concurrency need further testing.
- The vendor-neutral boundary avoids premature commitment to an unknown SAP interface, but the real adapter remains future work.
- The sample JSON enables an end-to-end job-order demonstration without an external dependency, but must be validated and mapped against real payloads.
- Docker Compose supports local demonstration, not production hosting. The prototype prioritizes send/receive traceability over live ERP connectivity, GPS and AI.

## What I would build next
1. Confirm the SAP product/edition, interface, authentication, data ownership and error-handling requirements; implement and test the corresponding adapter.
2. Obtain real job-order examples and a schema; agree mappings and add schema versioning, retries, idempotency and reconciliation.
3. Complete security and operational hardening, including backend authorization policy, secrets management, backups, monitoring and managed deployment.
4. Add integration, concurrency and failure-recovery tests for duplicate imports, partial receipts, discrepancies and inventory consistency.
5. Prioritize carrier/GPS visibility and analytics or AI only after validating operational needs.

The supplied brief requires a working, persistent send-then-receive prototype, a dummy job-order file and a note of no more than one page. It explicitly says real SAP integration is not required; the design should be scalable toward a future SAP connection.
