# Business rules and workflow

1. **Draft:** sender selects source, destination and SKU quantities. No stock changes yet.
2. **Dispatch:** only a draft can be dispatched. The API validates all requested quantities before changing stock. It decreases source on-hand, increases source in-transit, records UTC dispatch time and logs a stock movement.
3. **Partial receipt:** receiving manager records quantities physically received. A receipt cannot exceed outstanding quantity. Destination on-hand increases and source in-transit decreases by the same quantity.
4. **Received:** all item quantities have been received; the server records the final receipt timestamp.
5. **Discrepancy:** an optional note marks the transfer for review. Quantities are not silently adjusted.

Controls: source and destination must differ; creation quantities must be positive; dispatch cannot be repeated; receipt is allowed only after dispatch; receipt cannot exceed remaining quantity. Server timestamps are UTC and the browser renders local time. Corrections should be separate auditable movements.

KPIs: total transfers by lifecycle status; in-transit includes IN_TRANSIT, PARTIALLY_RECEIVED and DISCREPANCY; average transit time is mean dispatch-to-final-receipt duration for completed transfers. Carrier/on-time scores are omitted until verified carrier events and SLA/ETA data exist.

Returns should be a new reverse-direction transfer linked to the original in a production schema; the current prototype does not yet implement that link.