# Job order system integration — prototype contract

## Purpose

The existing job order system remains the system of record for the parent build. PlantFlow consumes a job-order message/file to associate SFG movements with the parent build. No real external system is connected.

## Sample exchange

The illustrative input is `docs/samples/job-order-JO-2026-001.json`. It contains a job order ID, parent build reference, parent product, planned quantity, unit and required SFG SKU quantities.

The existing system (or a future integration adapter) sends the JSON payload to:

`POST /api/job-orders/import`

The endpoint validates the payload, rejects duplicate job-order IDs, stores the original payload and records an import event. Imported records can be read using `GET /api/job-orders` and `GET /api/job-orders/{job_order_id}`.

When creating an SFG transfer, the user can supply the imported `job_order_id`. PlantFlow validates that the job order exists and stores the relationship on the transfer. Transfer detail responses include the parent-build reference. This provides traceability from the SFG movement back to the parent build.

## Data flow

1. Existing job order system creates/releases a parent-build order.
2. It exports the agreed JSON contract (the committed sample demonstrates the shape).
3. A future connector posts the payload to PlantFlow's authenticated import endpoint.
4. PlantFlow validates and persists the job order and import event.
5. PlantFlow users associate SFG transfers with that job order.
6. Dispatch and receipt events remain in PlantFlow and can be traced to the parent build.

## Ownership and limitations

- The job order system owns parent-build identity and planned quantities.
- PlantFlow owns SFG transfer dispatch/receipt events and its prototype inventory ledger.
- This prototype does not send completion, consumption or inventory updates back to the job order system.
- The JSON contract is illustrative, not an assertion about Indus's actual job-order schema.
- A production integration needs agreed field mappings, authentication, transport, retry/idempotency strategy, change handling and system-of-record rules.
- SAP S/4HANA remains a possible future ERP target, not a connected dependency.

## Manual API example

After signing in and obtaining a bearer token, send the sample JSON as the request body to `POST /api/job-orders/import` with `Authorization: Bearer <token>` and `Content-Type: application/json`.
