"""Enable PostgreSQL row-level security on all tenant-scoped tables.

No-op on SQLite (development); enforced on PostgreSQL in production. Combined
with the server-side `set_config('app.tenant_id', ...)` per request in
app/database/session.py, every query is restricted to the caller's tenant at
the database layer even if application scoping is bypassed.

Revision ID: rls001
Revises: 104338c8ead0
Create Date: 2026-10-17
"""
from alembic import op

revision = "rls001"
down_revision = "104338c8ead0"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "users",
    "research_projects",
    "research_sessions",
    "messages",
    "episodic_memories",
    "semantic_memories",
    "procedural_memories",
    "jobs",
    "agent_runs",
    "datasets",
    "artifacts",
    "validations",
    "experiments",
    "audit_logs",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite dev: application-layer scoping applies
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
        )
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")