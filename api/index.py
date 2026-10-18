"""Vercel ASGI entrypoint with persistent Postgres and request-owned jobs."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
database_url = os.environ.get("NOESIS_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
if not database_url:
    raise RuntimeError("Connect the free Neon database before deploying the backend")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
os.environ["NOESIS_DATABASE_URL"] = database_url
if not os.environ.get("NOESIS_JWT_SECRET"):
    raise RuntimeError("NOESIS_JWT_SECRET must be set before deployment")
os.environ["NOESIS_SERVERLESS"] = "true"
os.environ["NOESIS_WORKERS_ENABLED"] = "false"
os.environ["NOESIS_ARTIFACT_STORAGE"] = "database"
os.environ["NOESIS_ENVIRONMENT"] = "production"
os.environ["NOESIS_ARTIFACT_ROOT"] = "/tmp/noesis-artifacts"
os.environ["NOESIS_SIMULATION_SUBPROCESS_TIMEOUT_S"] = "180"
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

from app.database.session import init_db
init_db()
from app.main import app
