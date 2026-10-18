"""Episodic memory: records of completed experiments/investigations.

Idempotent: identical (tenant, objective, parameters, results) writes collapse
to the same record via content_hash. Every record carries provenance: tools
invoked, datasets, parameters, errors, code/env versions, artifacts.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EpisodicMemory
from app.memory.common import content_hash, store_embedding, vector_search

CODE_VERSION = "0.1.0"


def record_episode(
    db: Session,
    *,
    tenant_id: str,
    project_id: str,
    session_id: str,
    objective: str,
    assumptions: list[str] | None = None,
    dataset_ids: list[str] | None = None,
    tool_invocations: list[dict] | None = None,
    parameters: dict | None = None,
    status: str = "completed",
    results: dict | None = None,
    artifacts: list[str] | None = None,
    errors: list[dict] | None = None,
    env_version: str = "",
) -> EpisodicMemory:
    parameters = parameters or {}
    results = results or {}
    chash = content_hash(
        {"objective": objective, "parameters": parameters, "results": results, "status": status}
    )
    existing = db.scalar(
        select(EpisodicMemory).where(
            EpisodicMemory.tenant_id == tenant_id, EpisodicMemory.content_hash == chash
        )
    )
    if existing:
        return existing  # idempotent write
    mem = EpisodicMemory(
        tenant_id=tenant_id,
        project_id=project_id,
        session_id=session_id,
        objective=objective,
        assumptions=assumptions or [],
        dataset_ids=dataset_ids or [],
        tool_invocations=tool_invocations or [],
        parameters=parameters,
        status=status,
        results=results,
        artifacts=artifacts or [],
        errors=errors or [],
        code_version=CODE_VERSION,
        env_version=env_version,
        content_hash=chash,
    )
    store_embedding(mem, f"{objective} {json_dumps(parameters)} {json_dumps(results)}")
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj, default=str)[:4000]


def search_episodes(
    db: Session, *, tenant_id: str, query: str, limit: int = 5, status: str | None = None
) -> list[tuple[EpisodicMemory, float]]:
    return vector_search(
        db, EpisodicMemory, tenant_id=tenant_id, query=query, limit=limit,
        filters={"status": status},
    )


def get_episode(db: Session, *, tenant_id: str, episode_id: str) -> EpisodicMemory | None:
    return db.scalar(
        select(EpisodicMemory).where(
            EpisodicMemory.id == episode_id, EpisodicMemory.tenant_id == tenant_id
        )
    )


def list_episodes(
    db: Session, *, tenant_id: str, project_id: str | None = None, limit: int = 100
) -> list[EpisodicMemory]:
    stmt = select(EpisodicMemory).where(EpisodicMemory.tenant_id == tenant_id)
    if project_id:
        stmt = stmt.where(EpisodicMemory.project_id == project_id)
    stmt = stmt.order_by(EpisodicMemory.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())
