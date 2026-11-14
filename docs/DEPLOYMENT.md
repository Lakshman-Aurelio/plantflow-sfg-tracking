# Deployment guide

## Required Render environment variables

- `DATABASE_URL`: Neon PostgreSQL connection string.
- `CORS_ORIGINS`: exact Vercel origin, for example `https://your-project.vercel.app`.
- `JWT_SECRET`: generated high-entropy secret of at least 32 characters. Render's `generateValue: true` setting can generate it.
- `BOOTSTRAP_ADMIN_EMAIL`: initial administrator email.
- `BOOTSTRAP_ADMIN_PASSWORD`: unique password of at least 12 characters.

Do not put secrets in GitHub files or frontend environment variables.

## Neon PostgreSQL

1. Create a PostgreSQL project/database in Neon.
2. Copy the connection string from Neon and keep it private.
3. Set it as `DATABASE_URL` in the Render service environment.
4. Preserve the SSL parameters from the provider connection string.

## Render API

Deploy using `render.yaml`, or create a Python web service with:
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`

Alembic migrations run before the API starts. The first successful startup seeds demo records and creates the bootstrap administrator if the email is not already present. Changing the bootstrap password environment variable does not reset an existing user's password; change it through a controlled account-management procedure.

## Vercel frontend

1. Import the repository.
2. Set the project Root Directory to `frontend`.
3. Framework preset: Vite.
4. Build command: `npm run build`.
5. Output directory: `dist`.
6. Set `VITE_API_BASE_URL` to the Render API base URL ending in `/api`, e.g. `https://your-api.onrender.com/api`.
7. Redeploy after changing environment variables.

## Local Docker Compose

1. Copy the repository-root `.env.example` to `.env`.
2. Set a unique JWT secret, bootstrap administrator email and password.
3. Run `docker compose up --build`.

The Compose API service applies Alembic migrations before starting. The local PostgreSQL password in Compose is development-only and must never be reused in hosted environments.

## Security notes

- All API endpoints except health and login require a valid bearer token.
- Passwords are hashed using Argon2.
- Admin, manager and viewer roles are enforced for write operations.
- Manager/viewer inventory and transfer data is restricted to their assigned plant.
- Use HTTPS in hosted environments and keep the JWT secret private.
- Before production, add rate limiting, password reset/account recovery, token revocation, security monitoring, backups/restore drills and an external security review.
