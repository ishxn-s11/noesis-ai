# NOESIS AI — Deployment

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