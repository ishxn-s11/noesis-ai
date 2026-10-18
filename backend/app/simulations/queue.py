"""Durable DB-backed job queue: claim, retry, heartbeat, recovery.

Works on SQLite (dev; optimistic claim) and PostgreSQL (FOR UPDATE SKIP
LOCKED). Jobs survive process restarts; stale `running` jobs whose heartbeat
expired are requeued at worker startup — that is the recovery path the
orchestrator's durable handoff relies on.
"""
import json
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.database.models import Job
from app.database.session import SessionLocal

_IS_POSTGRES = False  # resolved lazily via engine dialect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    db: Session,
    *,
    tenant_id: str,
    kind: str,
    payload: dict,
    project_id: str = "",
    session_id: str = "",
    timeout_s: int = 600,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        tenant_id=tenant_id, kind=kind, payload=payload, project_id=project_id,
        session_id=session_id, timeout_s=timeout_s, max_attempts=max_attempts,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next(db: Session, worker_id: str, kinds: list[str] | None = None) -> Job | None:
    """Atomically claim the oldest queued job (or retryable failed job).

    PostgreSQL relies on FOR UPDATE SKIP LOCKED. SQLite ignores FOR UPDATE,
    so two workers CAN select the same row here; the claim is made atomic by
    a guarded UPDATE (compare-and-set on status='queued') where exactly one
    worker wins the queued->running transition — the loser sees rowcount 0
    and idles instead of double-executing the job.
    """
    stmt = select(Job).where(
        Job.status == "queued",
        Job.attempts < Job.max_attempts,
    )
    if kinds:
        stmt = stmt.where(Job.kind.in_(kinds))
    stmt = stmt.order_by(Job.created_at).limit(1)

    is_postgres = bool(db.bind and db.bind.dialect.name == "postgresql")
    if is_postgres:
        stmt = stmt.with_for_update(skip_locked=True)

    job = db.scalar(stmt)
    if job is None:
        db.rollback()
        return None

    if not is_postgres:
        # CAS claim: only the worker whose UPDATE actually flips the row owns it.
        res = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued",
                   Job.attempts < Job.max_attempts)
            .values(status="running", attempts=Job.attempts + 1,
                    locked_by=worker_id, heartbeat_at=_now(), error="",
                    started_at=func.coalesce(Job.started_at, _now()))
        )
        db.commit()
        if res.rowcount != 1:
            db.rollback()
            return None  # another worker won the claim
        db.refresh(job)
        return job

    job.status = "running"
    job.attempts += 1
    job.locked_by = worker_id
    job.heartbeat_at = _now()
    job.started_at = job.started_at or _now()
    job.error = ""
    db.commit()
    db.refresh(job)
    return job


def heartbeat(db: Session, job_id: str) -> None:
    db.execute(update(Job).where(Job.id == job_id).values(heartbeat_at=_now()))
    db.commit()


def complete(db: Session, job_id: str, result: dict) -> None:
    db.execute(
        update(Job).where(Job.id == job_id).values(
            status="succeeded", result=result, finished_at=_now(), error=""
        )
    )
    db.commit()


def fail(db: Session, job_id: str, error: str) -> str:
    """Mark failure; requeue if attempts remain, else terminal failure."""
    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        return "unknown"
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.error = error
        job.locked_by = ""
        new_status = "queued"
    else:
        job.status = "failed"
        job.error = error
        job.finished_at = _now()
        new_status = "failed"
    db.commit()
    return new_status


def recover_stale(db: Session, stale_after_s: int = 60) -> int:
    """Requeue running jobs whose heartbeat expired (worker crash recovery)."""
    cutoff = _now() - timedelta(seconds=stale_after_s)
    result = db.execute(
        update(Job)
        .where(Job.status == "running", or_(Job.heartbeat_at < cutoff, Job.heartbeat_at.is_(None)))
        .values(status="queued", locked_by="", error="recovered: heartbeat timeout")
    )
    db.commit()
    return result.rowcount or 0


def get_job(db: Session, job_id: str, tenant_id: str | None = None) -> Job | None:
    stmt = select(Job).where(Job.id == job_id)
    if tenant_id:
        stmt = stmt.where(Job.tenant_id == tenant_id)
    return db.scalar(stmt)


def job_public(job: Job) -> dict:
    return {
        "id": job.id, "kind": job.kind, "status": job.status, "attempts": job.attempts,
        "max_attempts": job.max_attempts, "error": job.error, "payload": job.payload,
        "result": job.result, "checkpoint": job.checkpoint, "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "session_id": job.session_id, "project_id": job.project_id,
    }
