"""SQLAlchemy models: tenancy/auth, research state, memory, jobs, artifacts."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ---------------------------------------------------------------------------
# Tenancy & auth
# ---------------------------------------------------------------------------


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40), default="researcher")  # researcher|admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant] = relationship()


# ---------------------------------------------------------------------------
# Research projects & sessions
# ---------------------------------------------------------------------------


class ResearchProject(Base, TimestampMixin):
    __tablename__ = "research_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    objective: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(80), default="celestial")  # stellar|celestial|cosmology|observation
    status: Mapped[str] = mapped_column(String(40), default="active")

    sessions: Mapped[list["ResearchSession"]] = relationship(back_populates="project")


class ResearchSession(Base, TimestampMixin):
    __tablename__ = "research_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("research_projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(40), default="open")  # open|closed
    summary: Mapped[str] = mapped_column(Text, default="")
    # Durable shared research state (versioned, JSON-serialized ResearchState)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[ResearchProject] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # researcher|agent|system
    agent: Mapped[str] = mapped_column(String(80), default="")
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # tool calls, evidence refs

    session: Mapped[ResearchSession] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# Durable memory
# ---------------------------------------------------------------------------


class EpisodicMemory(Base, TimestampMixin):
    __tablename__ = "episodic_memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    session_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    objective: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    dataset_ids: Mapped[list] = mapped_column(JSON, default=list)
    tool_invocations: Mapped[list] = mapped_column(JSON, default=list)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[list] = mapped_column(JSON, default=list)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    code_version: Mapped[str] = mapped_column(String(80), default="0.1.0")
    env_version: Mapped[str] = mapped_column(String(120), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    embedding: Mapped[str] = mapped_column(Text, default="")  # JSON float list (SQLite) / pgvector text fallback


class SemanticMemory(Base, TimestampMixin):
    __tablename__ = "semantic_memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # equation|definition|observation|constant|publication|hypothesis|finding
    status: Mapped[str] = mapped_column(String(40), default="established")  # established|assumption|hypothesis|verified
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)  # DOIs, URLs, dataset ids
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_quality: Mapped[str] = mapped_column(String(40), default="high")  # high|medium|low
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    embedding: Mapped[str] = mapped_column(Text, default="")


class ProceduralMemory(Base, TimestampMixin):
    __tablename__ = "procedural_memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    category: Mapped[str] = mapped_column(String(80))  # fits|orbit|statistics|classification|cleaning|integration
    description: Mapped[str] = mapped_column(Text, default="")
    workflow: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(40), default="pending")  # pending|approved|rejected
    validation_evidence: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    embedding: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------------------
# Durable jobs & agent runs
# ---------------------------------------------------------------------------


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    session_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    kind: Mapped[str] = mapped_column(String(80), index=True)  # simulation|experiment|report|research_run|archive_query
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # queued|running|succeeded|failed|cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_s: Mapped[int] = mapped_column(Integer, default=600)
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)  # orchestrator resume point
    locked_by: Mapped[str] = mapped_column(String(80), default="")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    agent: Mapped[str] = mapped_column(String(80), index=True)
    node: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|succeeded|failed|skipped
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # tool calls + artifact refs proving work
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Datasets, artifacts, validations, experiments, audit
# ---------------------------------------------------------------------------


class DatasetRecord(Base, TimestampMixin):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    source: Mapped[str] = mapped_column(String(120))  # exoplanet_archive|gaia|simbad|vizier|mast|heasarc|ned|user_upload|synthetic_demo
    identifier: Mapped[str] = mapped_column(String(400))
    description: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_id: Mapped[str] = mapped_column(String(36), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ArtifactContent(Base):
    """Persistent artifact bytes when no writable persistent disk is available."""
    __tablename__ = "artifact_contents"
    artifact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    session_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    kind: Mapped[str] = mapped_column(String(80))  # trajectory|plot|report|fits|table|bundle
    filename: Mapped[str] = mapped_column(String(400))
    path: Mapped[str] = mapped_column(String(800))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class ValidationResult(Base, TimestampMixin):
    __tablename__ = "validations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    experiment_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    check_name: Mapped[str] = mapped_column(String(200))
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    details: Mapped[str] = mapped_column(Text, default="")


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    name: Mapped[str] = mapped_column(String(300))
    objective: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending")  # pending|running|completed|failed
    job_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    results: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), default="")
    action: Mapped[str] = mapped_column(String(120))
    resource: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


__all__ = [
    "Tenant",
    "User",
    "ResearchProject",
    "ResearchSession",
    "Message",
    "EpisodicMemory",
    "SemanticMemory",
    "ProceduralMemory",
    "Job",
    "AgentRun",
    "DatasetRecord",
    "Artifact",
    "ValidationResult",
    "Experiment",
    "AuditLog",
    "UniqueConstraint",
]
