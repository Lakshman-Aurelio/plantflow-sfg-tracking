# PlantFlow — SFG Transfer Tracking

A lightweight prototype for tracking semi-finished-goods transfers across three plants. React + TypeScript frontend, FastAPI backend and SQLite demo database.

## Features
- Create transfers with multiple SKU/quantity lines.
- Dispatch and receive actions record server-generated UTC timestamps.
- Dispatch reserves stock at source; receipt adds stock at destination. Partial receipt is supported.
- Search by transfer number or SKU; filter by status and date range.
- Transfer event history, dashboard metrics and CSV export.
- Three clearly labelled demo plants and sample SKUs are seeded automatically.

## Run on Windows 11
Requires Python 3.10+ and Node.js 20+.

API terminal:
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```
UI terminal:
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. API docs: http://127.0.0.1:8000/docs.

The database is created at `backend/plantflow.db`; delete it to reset demo data.

## Prototype boundaries
Plant names and SKUs are demo records. GPS is manual checkpoint only; SAP, carrier APIs and AI are not connected. Authentication, role-based access, migrations, backups and deployment hardening are required before production. Inventory valuation is not shown until verified unit-cost data is supplied. See `docs/`.