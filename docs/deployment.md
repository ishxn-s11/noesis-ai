# NOESIS AI — Deployment

## Free Vercel + Neon deployment

The root `vercel.json` serves the Vite frontend and the Python API together.
Set the Vercel project root to the repository root, framework to Other, build
command to `npm --prefix frontend ci && npm --prefix frontend run build`, and
output directory to `frontend/dist`. Connect a **Free** Neon Postgres database
through Vercel Storage. Keep `DATABASE_URL` server-only, set a random sensitive
`NOESIS_JWT_SECRET`, and set `VITE_SERVERLESS=true`. Leave `VITE_API_BASE_URL`
empty for this same-origin deployment. No Render resource is needed.

This mode stores artifact bytes in Postgres instead of the ephemeral function
filesystem. The first backend start initializes the new database schema under
a Postgres advisory lock. Existing production databases should still use
reviewed schema migrations. Auth, research state, and artifact content survive
function restarts. The database's free storage/compute quotas still apply.

The browser starts a separate authenticated `/api/jobs/{id}/execute` request
when it receives or polls a queued job. A database conditional claim prevents
duplicate execution. Each request owns one worker subprocess with a 240-second
deadline; oversized jobs fail explicitly. Interrupted jobs can be retried when
the user returns and polls them after five minutes. Keep the app open while
starting research. There is no continuously running background worker or
guaranteed unattended execution in this mode. Agent state and checkpoints
persist; process-local event broadcasts are not shared between functions, so
the UI also polls saved job/session state.

Keep uploads and generated artifacts below 4 MB to fit Vercel's response limit.
Use small simulations and parameter sweeps. The free tier is intended for
personal/noncommercial use within Vercel and Neon allowances; no paid plan,
automatic upgrade, or external LLM provider is enabled by this configuration.
The root Python requirements omit unused pandas/astroquery and development
test dependencies to reduce the function bundle.

## Vercel frontend + Render backend

The repository includes `render.yaml` for a single Docker API instance with
one in-process research worker. Its 1 GB persistent disk stores both SQLite
and research artifacts under `/srv/data`. This is a small-instance deployment;
do not scale it to multiple instances while it uses SQLite/local artifacts.
Redis and FalkorDB are optional and are not provisioned by this Blueprint.
Without LLM credentials, research uses the existing deterministic offline mode.

Render's `1c-2g` compute and persistent disk are paid resources. Review the
current price in Render before provisioning; adding this file alone does not
create resources or start billing. See https://render.com/pricing and
https://render.com/docs/disks. Disk-backed deployments briefly interrupt the
service during a restart/deploy. Keep independent database backups.

1. Connect the repository to Render and create a Blueprint from `render.yaml`
   on the merged `main` branch. It builds `backend/Dockerfile` from the repo
   root, applies migrations at startup, and generates `NOESIS_JWT_SECRET`.
2. Wait for the API's `/health` endpoint to report `status: ok` and
   `database: ok`. Record the actual HTTPS URL assigned by Render.
3. In the existing Vercel `noesis-ai` project, set Root Directory to `frontend`,
   framework to Vite, install command to `npm ci`, build command to
   `npm run build`, and output directory to `dist`.
4. Set `VITE_API_BASE_URL` in Vercel to the Render origin (for example,
   `https://your-assigned-service.onrender.com`), without a trailing `/api`.
   This value is public build configuration, not a secret. Redeploy the frontend
   after changing it; Vite embeds it at build time.
5. Connect GitHub in Vercel account authentication settings, then connect
   `ishxn-s11/noesis-ai` in the project's Git settings. Use `main` for
   production. Render redeploys backend changes from `main` as well.
6. Verify registration/login, create a research session, submit a simulation,
   observe job events, and download its artifact from the live frontend.

`NOESIS_CORS_ORIGINS` in the Blueprint allows the current production Vercel
domains and localhost. Add any new frontend custom domain explicitly before
using it. Preview URLs are not wildcard-allowed. All browser API, upload,
download, and streaming requests use `VITE_API_BASE_URL`; an empty value keeps
the local same-origin Vite proxy behavior.

Account sign-in and GitHub authorization must be completed by the account
owner. Never put GitHub tokens, backend secrets, or private environment files
in the repository or `VITE_*` variables.

## Development (zero external dependencies)

```bash
# Backend — SQLite default, no Postgres/Redis required
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env              # edit as needed
alembic upgrade head                 # create schema (16 tables)
NOESIS_WORKERS_ENABLED=true uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

`vite.config.ts` proxies `/api` to `http://localhost:8000`.

## Tests

```bash
cd backend && pytest tests/ -q       # 37 tests
cd frontend && ./node_modules/.bin/tsc -b --noEmit
cd frontend && npm run build

# Full reproducible end-to-end demo (backend must be running):
python scripts/e2e_demo.py --base http://127.0.0.1:8000
```

## Production (Docker Compose)

```bash
cp .env.example .env                 # set NOESIS_JWT_SECRET!
docker compose up --build -d
# Host-port overrides when the defaults are taken (verified working values):
# NOESIS_BACKEND_PORT=8010 NOESIS_FRONTEND_PORT=8081 NOESIS_GRAPHDB_UI_PORT=13001 \
#   docker compose up -d
```

Services: PostgreSQL (pgvector), Redis, **FalkorDB** (context layer, exposed
via `NOESIS_GRAPHDB_URL=graphdb:6379`; browser UI at http://localhost:3000),
backend, and the nginx-served frontend.

FalkorDB durability: the compose service runs AOF (`--appendonly yes`,
`appendfsync everysec`) plus RDB snapshots, with the `falkordb-data` volume
mounted at `/var/lib/falkordb/data` (the image's own `--dir` overrides
`REDIS_ARGS`, so the mount path matters). Graph state survives container
recreation and Docker engine restarts — verified in test.

- Backend: http://localhost:8000 (OpenAPI at `/docs`)
- Frontend: http://localhost:8080 (nginx, `/api` proxied to backend)
- FalkorDB browser UI: http://localhost:3000

The backend container runs `alembic upgrade head` on start.

## Migrations

```bash
cd backend
alembic upgrade head                 # apply
alembic revision --autogenerate -m "..."   # generate (dev only)
```

The RLS migration (`20261017_rls_policies`) applies only on PostgreSQL.

## Environment variables

All `NOESIS_*` variables are documented in `.env.example` with defaults.
Important production changes:

| Variable | Production value |
|---|---|
| `NOESIS_JWT_SECRET` | long random string |
| `NOESIS_DATABASE_URL` | `postgresql+psycopg://...` |
| `NOESIS_REDIS_URL` | `redis://redis:6379/0` |
| `NOESIS_GRAPHDB_URL` | `graphdb:6379` (empty disables the context layer) |
| `NOESIS_ENVIRONMENT` | `production` |
| `NOESIS_CORS_ORIGINS` | your frontend origin(s) |
