"""NOESIS AI FastAPI application.

Lifespan starts in-process durable workers (NOESIS_WORKERS_ENABLED) unless
disabled (e.g., when running a separate workers.runner process in Docker).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import settings
from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("noesis.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database.session import init_db

    init_db()  # dev: create tables; production uses Alembic migrations
    workers = None
    if settings.workers_enabled:
        from workers.runner import start_workers

        stop_event, threads = start_workers(settings.worker_count)
        workers = (stop_event, threads)
        logger.info("started %d in-process worker(s)", len(threads))
    yield
    if workers:
        stop_event, threads = workers
        stop_event.set()
        for t in threads:
            t.join(timeout=5)
        logger.info("workers stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NOESIS AI — Astrophysics & Cosmology Research Platform",
        description=(
            "Autonomous multi-agent scientific research platform: durable memory, "
            "real N-body/cosmology/observation tooling, evidence-checked agent runs."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    from app.api import (agent_routes, auth_routes, explainer_routes, memory_routes,
                         research_routes, simulation_routes)

    prefix = settings.api_prefix
    app.include_router(auth_routes.router, prefix=prefix)
    app.include_router(research_routes.router, prefix=prefix)
    app.include_router(memory_routes.router, prefix=prefix)
    app.include_router(simulation_routes.router, prefix=prefix)
    app.include_router(agent_routes.router, prefix=prefix)
    app.include_router(explainer_routes.router, prefix=prefix)

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        from sqlalchemy import text

        from app.database.session import engine

        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            db_ok = False
            return {"status": "degraded", "database": str(exc)[:120],
                    "version": __version__}
        return {"status": "ok", "database": "ok", "version": __version__,
                "environment": settings.environment,
                "workers_enabled": settings.workers_enabled,
                "llm_mode": "configured" if settings.llm_base_url else "deterministic_offline"}

    return app


app = create_app()