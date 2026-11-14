# Business rules and workflow

1. **Job order import:** the existing job order system owns the parent build. It can send a JSON payload using the documented sample contract. PlantFlow validates and stores the job order, original payload and import event. Duplicate job-order IDs are rejected.
2. **Draft:** sender selects source, destination, SKU quantities and optionally an imported parent-build job order. The job-order reference is retained on the transfer. No stock changes yet.
3. **Dispatch:** only a draft can be dispatched. The API validates all requested quantities before changing stock. It decreases source on-hand, increases source in-transit, records UTC dispatch time and logs a stock movement.
4. **Partial receipt:** receiving manager records quantities physically received. A receipt cannot exceed outstanding quantity. Destination on-hand increases and source in-transit decreases by the same quantity.
5. **Received:** all item quantities have been received; the server records the final receipt timestamp.
6. **Discrepancy:** an optional note marks the transfer for review. Quantities are not silently adjusted.

Controls: source and destination must differ; creation quantities must be positive; dispatch cannot be repeated; receipt is allowed only after dispatch; receipt cannot exceed remaining quantity. Server timestamps are UTC and the browser renders local time. Corrections should be separate auditable movements.

The job order system remains the parent-build system of record. PlantFlow owns SFG movement events and the prototype inventory ledger. This prototype does not write receipts, consumption or completion status back to the job order system.

KPIs: total transfers by lifecycle status; in-transit includes IN_TRANSIT, PARTIALLY_RECEIVED and DISCREPANCY; average transit time is mean dispatch-to-final-receipt duration for completed transfers. Carrier/on-time scores are omitted until verified carrier events and SLA/ETA data exist.

Returns should be a new reverse-direction transfer linked to the original in a production schema; the current prototype does not yet implement that link.
