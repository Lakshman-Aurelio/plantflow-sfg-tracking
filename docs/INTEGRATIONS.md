# Integration roadmap — no external system is connected

| Capability | Current state | Production requirement |
|---|---|---|
| SAP / ERP | Vendor-neutral adapter contract; SAP S/4HANA connector is a planned placeholder | Confirm Indus SAP product/edition, deployment model, released APIs, auth, network route, plant/material/storage-location mappings and system-of-record rules |
| Inventory | Demo ledger updates on dispatch/receipt | ERP reconciliation, reservations, adjustment rules and conflict ownership |
| GPS | Manual coordinate checkpoint endpoint | Carrier/device feed, shipment mapping and location retention policy |
| Valuation | Not displayed | Verified unit cost and currency from ERP/finance |
| Transfer performance | Average completed transit duration | Agreed SLA and reliable event capture |
| Carrier performance | Not calculated | Carrier master, assignment and pickup/delivery events |
| Returns | Not implemented | Linked reverse transfer, reason codes, inspection and approvals |
| AI assistant | Not connected | Read-only authorized retrieval, audit trail and cited data freshness; no autonomous stock changes |

## SAP S/4HANA discovery checklist

Before building the connector, ask Indus:
1. Is the system SAP S/4HANA Cloud Public Edition, Private Edition or on-premise?
2. Which released APIs or integration middleware are enabled (for example, SAP Integration Suite)?
3. What authentication and network connectivity are permitted?
4. Which SAP objects represent plants, storage locations, materials, stock and stock transport orders?
5. Which system owns each transaction and what is the approved sync direction?
6. What are the rules for partial goods issue, goods receipt, reversals and reconciliation?

The adapter interface is deliberately independent of SAP. The current SAP S/4HANA module is a configuration placeholder and raises a clear not-implemented error; it does not call SAP or simulate a successful sync.

The prototype does not claim live GPS, SAP synchronization, AI answers, carrier scores or valuation.
