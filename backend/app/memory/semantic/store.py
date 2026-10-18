"""Semantic memory: evidence-backed scientific knowledge with provenance.

Critical invariant: `status` distinguishes established knowledge, model
assumptions, generated hypotheses, and experimentally verified findings.
Nothing is silently promoted: promote() requires evidence references and
records a new version linked to its parent.
"""
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import NotFoundErr, ValidationErr
from app.database.models import SemanticMemory
from app.memory.common import content_hash, store_embedding, vector_search


def _latest_only(stmt):
    """Exclude superseded versions (rows another row points to as parent)."""
    child = aliased(SemanticMemory)
    return stmt.where(~exists(select(child.id).where(child.parent_id == SemanticMemory.id)))

_ALLOWED_STATUSES = {"established", "assumption", "hypothesis", "verified"}
_ALLOWED_KINDS = {
    "equation", "definition", "observation", "constant", "publication",
    "hypothesis", "finding",
}


def add_knowledge(
    db: Session,
    *,
    tenant_id: str,
    kind: str,
    title: str,
    content: str,
    status: str = "established",
    source_refs: list[str] | None = None,
    confidence: float = 1.0,
    evidence_quality: str = "high",
) -> SemanticMemory:
    if kind not in _ALLOWED_KINDS:
        raise ValidationErr(f"Unknown knowledge kind: {kind}")
    if status not in _ALLOWED_STATUSES:
        raise ValidationErr(f"Unknown knowledge status: {status}")
    source_refs = source_refs or []
    if status in {"established", "verified"} and not source_refs:
        raise ValidationErr(
            "established/verified knowledge requires at least one source reference"
        )
    chash = content_hash({"kind": kind, "title": title, "content": content})
    existing = db.scalar(
        select(SemanticMemory).where(
            SemanticMemory.tenant_id == tenant_id, SemanticMemory.content_hash == chash
        )
    )
    if existing:
        return existing
    mem = SemanticMemory(
        tenant_id=tenant_id, kind=kind, status=status, title=title, content=content,
        source_refs=source_refs, confidence=confidence, evidence_quality=evidence_quality,
        content_hash=chash,
    )
    store_embedding(mem, f"{title} {content} {' '.join(source_refs)}")
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def promote(
    db: Session,
    *,
    tenant_id: str,
    memory_id: str,
    new_status: str,
    evidence_refs: list[str],
    confidence: float | None = None,
) -> SemanticMemory:
    """Create a new version of a memory with upgraded status.

    Promotion to `verified` demands experimental evidence references; the
    original record is preserved (version chain via parent_id).
    """
    if new_status not in _ALLOWED_STATUSES:
        raise ValidationErr(f"Unknown knowledge status: {new_status}")
    if new_status == "verified" and not evidence_refs:
        raise ValidationErr("Promotion to 'verified' requires experimental evidence")
    original = get_knowledge(db, tenant_id=tenant_id, memory_id=memory_id)
    if not original:
        raise NotFoundErr("Semantic memory not found")
    versioned = SemanticMemory(
        tenant_id=tenant_id,
        kind=original.kind,
        status=new_status,
        title=original.title,
        content=original.content,
        source_refs=list(original.source_refs) + list(evidence_refs),
        confidence=confidence if confidence is not None else original.confidence,
        evidence_quality="high" if evidence_refs else original.evidence_quality,
        version=original.version + 1,
        parent_id=original.id,
        content_hash=original.content_hash,
        embedding=original.embedding,
    )
    db.add(versioned)
    db.commit()
    db.refresh(versioned)
    return versioned


def get_knowledge(db: Session, *, tenant_id: str, memory_id: str) -> SemanticMemory | None:
    return db.scalar(
        select(SemanticMemory).where(
            SemanticMemory.id == memory_id, SemanticMemory.tenant_id == tenant_id
        )
    )


def search_knowledge(
    db: Session, *, tenant_id: str, query: str, limit: int = 5,
    kind: str | None = None, status: str | None = None,
) -> list[tuple[SemanticMemory, float]]:
    return vector_search(
        db, SemanticMemory, tenant_id=tenant_id, query=query, limit=limit,
        filters={"kind": kind, "status": status},
    )


def list_knowledge(
    db: Session, *, tenant_id: str, kind: str | None = None, status: str | None = None,
    limit: int = 200,
) -> list[SemanticMemory]:
    stmt = select(SemanticMemory).where(SemanticMemory.tenant_id == tenant_id)
    stmt = _latest_only(stmt)
    if kind:
        stmt = stmt.where(SemanticMemory.kind == kind)
    if status:
        stmt = stmt.where(SemanticMemory.status == status)
    stmt = stmt.order_by(SemanticMemory.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())
