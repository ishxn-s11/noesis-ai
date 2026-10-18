"""Procedural memory: reusable research workflows.

Invariant: a workflow only becomes `approved` after successful execution with
validation evidence (approve() requires a passing validation record).
"""
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import NotFoundErr, ValidationErr
from app.database.models import ProceduralMemory
from app.memory.common import content_hash, store_embedding, vector_search


def _latest_only(stmt):
    """Return only non-superseded versions of each procedure."""
    child = aliased(ProceduralMemory)
    return stmt.where(~exists(select(child.id).where(child.parent_id == ProceduralMemory.id)))


def save_procedure(
    db: Session,
    *,
    tenant_id: str,
    name: str,
    category: str,
    workflow: dict,
    description: str = "",
) -> ProceduralMemory:
    chash = content_hash({"name": name, "workflow": workflow})
    existing = db.scalar(
        select(ProceduralMemory).where(
            ProceduralMemory.tenant_id == tenant_id, ProceduralMemory.content_hash == chash
        )
    )
    if existing:
        return existing
    mem = ProceduralMemory(
        tenant_id=tenant_id, name=name, category=category, description=description,
        workflow=workflow, validation_status="pending", content_hash=chash,
    )
    store_embedding(mem, f"{name} {category} {description} {str(workflow)[:2000]}")
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def approve(
    db: Session, *, tenant_id: str, procedure_id: str, evidence: dict
) -> ProceduralMemory:
    """Approve a procedure; requires successful-execution evidence."""
    proc = get_procedure(db, tenant_id=tenant_id, procedure_id=procedure_id)
    if not proc:
        raise NotFoundErr("Procedure not found")
    if not evidence.get("executed") or not evidence.get("validated"):
        raise ValidationErr(
            "Approval requires evidence: {executed: true, validated: true, ...}"
        )
    updated = ProceduralMemory(
        tenant_id=tenant_id,
        name=proc.name,
        category=proc.category,
        description=proc.description,
        workflow=proc.workflow,
        validation_status="approved",
        validation_evidence=list(proc.validation_evidence) + [evidence],
        version=proc.version + 1,
        parent_id=proc.id,
        content_hash=proc.content_hash,
        embedding=proc.embedding,
    )
    db.add(updated)
    db.commit()
    db.refresh(updated)
    return updated


def get_procedure(db: Session, *, tenant_id: str, procedure_id: str) -> ProceduralMemory | None:
    return db.scalar(
        select(ProceduralMemory).where(
            ProceduralMemory.id == procedure_id, ProceduralMemory.tenant_id == tenant_id
        )
    )


def search_procedures(
    db: Session, *, tenant_id: str, query: str, limit: int = 5,
    category: str | None = None, approved_only: bool = False,
) -> list[tuple[ProceduralMemory, float]]:
    results = vector_search(
        db, ProceduralMemory, tenant_id=tenant_id, query=query, limit=limit * 2,
        filters={"category": category},
    )
    if approved_only:
        results = [(p, s) for p, s in results if p.validation_status == "approved"]
    return results[:limit]


def list_procedures(
    db: Session, *, tenant_id: str, category: str | None = None, limit: int = 200
) -> list[ProceduralMemory]:
    stmt = select(ProceduralMemory).where(ProceduralMemory.tenant_id == tenant_id)
    stmt = _latest_only(stmt)
    if category:
        stmt = stmt.where(ProceduralMemory.category == category)
    stmt = stmt.order_by(ProceduralMemory.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())
