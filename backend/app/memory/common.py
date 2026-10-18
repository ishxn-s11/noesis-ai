"""Shared memory utilities: hashing, embedding persistence, vector search, versioning."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import cosine_similarity, embed_text


def content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def dump_embedding(vec: list[float]) -> str:
    return json.dumps([round(v, 7) for v in vec])


def load_embedding(raw: str) -> list[float]:
    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []


def vector_search(
    db: Session,
    model,
    *,
    tenant_id: str,
    query: str,
    limit: int = 5,
    filters: dict | None = None,
) -> list[tuple[object, float]]:
    """Cosine similarity search over stored embeddings, tenant-scoped.

    Superseded versions (rows another row points to via parent_id) are
    excluded so retrieval always surfaces the current version.
    """
    from sqlalchemy import exists, select
    from sqlalchemy.orm import aliased

    stmt = select(model).where(model.tenant_id == tenant_id)
    if hasattr(model, "parent_id"):
        child = aliased(model)
        stmt = stmt.where(~exists(select(child.id).where(child.parent_id == model.id)))
    for field, value in (filters or {}).items():
        if hasattr(model, field) and value is not None:
            stmt = stmt.where(getattr(model, field) == value)
    rows = db.scalars(stmt).all()
    query_vec = embed_text(query)
    scored = []
    for row in rows:
        sim = cosine_similarity(query_vec, load_embedding(row.embedding))
        scored.append((row, sim))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def store_embedding(obj, text: str) -> None:
    obj.embedding = dump_embedding(embed_text(text))
