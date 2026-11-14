# PlantFlow — SFG Transfer Tracking

PlantFlow is a prototype for tracking semi-finished-goods (SFG) transfers and inventory across three plants.

## Target deployment

- **Source:** public GitHub repository
- **Frontend:** React + TypeScript + Vite on Vercel
- **Backend:** FastAPI on Render
- **Database:** PostgreSQL on Neon
- **Local development:** Docker Compose with PostgreSQL

The application now uses PostgreSQL. SQLite is no longer the application database.

## Features in this prototype

- Create transfers with multiple SKU/quantity lines.
- Dispatch and receive actions record server-generated UTC timestamps.
- Dispatch moves units from source on-hand to source in-transit; receipt moves accepted units into destination stock.
- Partial receipts, discrepancy notes, event history and stock movement records.
- Search by transfer number or SKU; filter by status and date range.
- Dashboard metrics and CSV export.
- Three demo plants and sample SKUs are seeded into an empty database.

## Run locally on Windows 11

Install Docker Desktop, then from the repository root run:

```powershell
docker compose up --build
```

Open:
- UI: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

Stop services with `Ctrl+C`, then optionally run `docker compose down`. To remove the local database volume and reset demo data, run `docker compose down -v`.

### Run frontend/backend separately

Start PostgreSQL separately and set `DATABASE_URL` in the backend environment. Then:

Backend:
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="postgresql://plantflow:plantflow_dev_password@localhost:5432/plantflow"
$env:CORS_ORIGINS="http://localhost:5173"
uvicorn app.main:app --reload
```

Frontend in a second terminal:
```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://localhost:8000/api"
npm run dev
```

## Deploy

1. Create a Neon PostgreSQL database and copy its connection string.
2. Deploy the `backend` directory to Render using `backend/Dockerfile` or the Python build/start commands in `render.yaml`. Set `DATABASE_URL` to the Neon connection string and `CORS_ORIGINS` to the exact Vercel production origin.
3. Deploy the `frontend` directory to Vercel. Set `VITE_API_BASE_URL` to `https://YOUR-RENDER-SERVICE.onrender.com/api`.
4. Redeploy the frontend after changing its environment variables.

Do not commit real database URLs, credentials, API keys or SAP secrets. See `.env.example` files and `docs/DEPLOYMENT.md`.

## SAP integration direction

SAP version is not yet confirmed by Indus. The codebase therefore defines an ERP adapter boundary and documents SAP S/4HANA as the first planned connector, without pretending that a live SAP connection exists. The actual connector requires confirmation of the SAP edition, enabled APIs, authentication method, network access and master-data mappings.

## Production limitations

This is still a prototype, not a production-ready enterprise inventory system. Authentication, plant-scoped authorization, approvals, operational monitoring, backup/restore procedures, formal migration review, idempotency keys, ERP reconciliation and security testing must be completed before live plant use. GPS is manual checkpoint only. SAP, carrier APIs and AI are not connected. Inventory valuation is not shown without verified cost and currency data.
