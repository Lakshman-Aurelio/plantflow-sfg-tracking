# Deployment guide

## Neon PostgreSQL

1. Create a PostgreSQL project/database in Neon.
2. Copy the connection string from Neon and keep it private.
3. Set it as DATABASE_URL in the Render service environment.
4. Use the pooled connection string if recommended by the current Neon console for application traffic. Confirm SSL parameters are retained.

## Render API

Deploy the repository using render.yaml, or create a Python web service with:
- Root directory: backend
- Build command: pip install -r requirements.txt
- Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
- Health check: /api/health

Set DATABASE_URL to the Neon PostgreSQL connection string and CORS_ORIGINS to the exact Vercel origin, e.g. https://your-project.vercel.app. Additional approved origins may be comma-separated.

## Vercel frontend

1. Import the GitHub repository.
2. Set the project Root Directory to frontend.
3. Framework preset: Vite.
4. Build command: npm run build.
5. Output directory: dist.
6. Set VITE_API_BASE_URL to the Render API base URL ending in /api, e.g. https://your-api.onrender.com/api.
7. Redeploy after setting or changing environment variables.

## Local Docker Compose

From the repository root run:

```powershell
docker compose up --build
```

The local stack starts PostgreSQL, FastAPI and Vite. It uses a development-only password from docker-compose.yml; never reuse it in hosted environments.

## Important

Do not commit credentials or copy a production Neon URL into Git. The current schema initializer creates the initial schema on first startup. A reviewed formal migration workflow is required before evolving the production schema. Configure backups, access controls and monitoring before any operational deployment.
