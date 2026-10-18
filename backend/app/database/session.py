"""Engine/session factory supporting SQLite (dev) and PostgreSQL (prod).

For PostgreSQL the session sets `app.tenant_id` so row-level security policies
(enforced in migrations) restrict every query to the current tenant. With
SQLite, tenant scoping is enforced server-side in the repository/query layer.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

_IS_POSTGRES = settings.database_url.startswith(("postgres", "postgresql"))

connect_args = {"check_same_thread": False} if not _IS_POSTGRES else {}
engine_kwargs = {"future": True}
if settings.serverless and _IS_POSTGRES:
    engine_kwargs["poolclass"] = NullPool
if not _IS_POSTGRES:
    engine_kwargs["connect_args"] = connect_args
    if not _IS_POSTGRES:
        # wait for concurrent writers instead of failing immediately
        engine_kwargs["connect_args"] = {**connect_args}

engine = create_engine(settings.database_url, **engine_kwargs)

if not _IS_POSTGRES:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

if _IS_POSTGRES:

    @event.listens_for(engine, "connect")
    def _set_tenant_guc(dbapi_conn, _record):  # noqa: ANN001
        # Placeholder; real value is set per-request via set_tenant().
        pass


def set_tenant(db: Session, tenant_id: str | None) -> None:
    """Bind the PostgreSQL RLS GUC for this session (no-op on SQLite)."""
    if _IS_POSTGRES:
        db.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": tenant_id or ""})


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for development/SQLite. Alembic owns production schema."""
    from app.database import models  # noqa: F401
    from app.database.base import Base

    if settings.serverless and _IS_POSTGRES:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(846322017)"))
            Base.metadata.create_all(bind=connection)
    else:
        Base.metadata.create_all(bind=engine)
