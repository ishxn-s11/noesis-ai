"""Scientific memory explorer API: episodic, semantic, procedural."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import CurrentUser, get_current_user
from app.core.errors import NotFoundErr, ValidationErr
from app.database.session import get_db, set_tenant
from app.memory import episodic as epi
from app.memory import procedural as proc
from app.memory import semantic as sem

router = APIRouter(prefix="/memory", tags=["memory"])


def _db(raw_db: Session, user: CurrentUser) -> Session:
    set_tenant(raw_db, user.tenant_id)
    return raw_db


# --- episodic -----------------------------------------------------------------

@router.get("/episodic", summary="List/search experiment records")
def list_episodic(q: str = Query("", max_length=500),
                  status: str | None = None,
                  user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    db = _db(db, user)
    if q.strip():
        rows = epi.search_episodes(db, tenant_id=user.tenant_id, query=q, limit=50, status=status)
        items = [(m, s) for m, s in rows]
    else:
        items = [(m, None) for m in epi.list_episodes(db, tenant_id=user.tenant_id)]
        if status:
            items = [(m, s) for m, s in items if m.status == status]
    return [{**_epi(m), "score": round(s, 4) if s is not None else None} for m, s in items]


@router.get("/episodic/{memory_id}")
def get_episodic(memory_id: str, user: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = epi.get_episode(db, tenant_id=user.tenant_id, memory_id=memory_id)
    if not m:
        raise NotFoundErr("Episode not found")
    return _epi(m)


def _epi(m) -> dict:
    return {"id": m.id, "objective": m.objective, "status": m.status,
            "assumptions": m.assumptions, "dataset_ids": m.dataset_ids,
            "parameters": m.parameters, "results": m.results, "artifacts": m.artifacts,
            "errors": m.errors, "tool_invocations": m.tool_invocations,
            "project_id": m.project_id, "session_id": m.session_id,
            "code_version": m.code_version, "env_version": m.env_version,
            "created_at": m.created_at.isoformat(),
            "updated_at": m.updated_at.isoformat()}


# --- semantic -----------------------------------------------------------------

class KnowledgeIn(BaseModel):
    kind: str
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=1, max_length=8000)
    status: str = "established"
    source_refs: list[str] = []
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence_quality: str = "high"


@router.post("/semantic", summary="Write knowledge (established needs sources)")
def add_semantic(body: KnowledgeIn, user: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = sem.add_knowledge(db, tenant_id=user.tenant_id, kind=body.kind, title=body.title,
                          content=body.content, status=body.status,
                          source_refs=body.source_refs, confidence=body.confidence,
                          evidence_quality=body.evidence_quality)
    return _sem(m)


class PromoteIn(BaseModel):
    new_status: str
    evidence_refs: list[str] = []
    confidence: float | None = None


@router.post("/semantic/{memory_id}/promote", summary="Versioned status promotion")
def promote_semantic(memory_id: str, body: PromoteIn,
                     user: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = sem.promote(db, tenant_id=user.tenant_id, memory_id=memory_id,
                    new_status=body.new_status, evidence_refs=body.evidence_refs,
                    confidence=body.confidence)
    return _sem(m)


@router.get("/semantic", summary="Search/list semantic knowledge")
def list_semantic(q: str = Query("", max_length=500),
                  kind: str | None = None, status: str | None = None,
                  user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    db = _db(db, user)
    if q.strip():
        items = sem.search_knowledge(db, tenant_id=user.tenant_id, query=q,
                                     limit=50, kind=kind, status=status)
        return [{**_sem(m), "score": round(s, 4)} for m, s in items]
    return [_sem(m) for m in sem.list_knowledge(db, tenant_id=user.tenant_id,
                                                kind=kind, status=status)]


@router.get("/semantic/{memory_id}")
def get_semantic(memory_id: str, user: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = sem.get_knowledge(db, tenant_id=user.tenant_id, memory_id=memory_id)
    if not m:
        raise NotFoundErr("Knowledge not found")
    return _sem(m)


def _sem(m) -> dict:
    return {"id": m.id, "kind": m.kind, "status": m.status, "title": m.title,
            "content": m.content, "source_refs": m.source_refs,
            "confidence": m.confidence, "evidence_quality": m.evidence_quality,
            "version": m.version, "parent_id": m.parent_id,
            "created_at": m.created_at.isoformat()}


# --- procedural ----------------------------------------------------------------

class ProcedureIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    category: str
    description: str = ""
    workflow: dict = Field(default_factory=dict)


@router.post("/procedural", summary="Save a workflow (starts as pending)")
def add_procedure(body: ProcedureIn, user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = proc.save_procedure(db, tenant_id=user.tenant_id, name=body.name,
                            category=body.category, workflow=body.workflow,
                            description=body.description)
    return _proc(m)


class ApproveIn(BaseModel):
    evidence: dict


@router.post("/procedural/{memory_id}/approve", summary="Approve (requires execution evidence)")
def approve_procedure(memory_id: str, body: ApproveIn,
                      user: CurrentUser = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    m = proc.approve(db, tenant_id=user.tenant_id, procedure_id=memory_id,
                     evidence=body.evidence)
    return _proc(m)


@router.get("/procedural")
def list_procedural(q: str = Query("", max_length=500),
                    category: str | None = None,
                    approved_only: bool = False,
                    user: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> list[dict]:
    db = _db(db, user)
    if q.strip():
        items = proc.search_procedures(db, tenant_id=user.tenant_id, query=q,
                                       limit=50, category=category,
                                       approved_only=approved_only)
        return [{**_proc(m), "score": round(s, 4)} for m, s in items]
    rows = proc.list_procedures(db, tenant_id=user.tenant_id, category=category)
    if approved_only:
        rows = [r for r in rows if r.validation_status == "approved"]
    return [_proc(m) for m in rows]


def _proc(m) -> dict:
    return {"id": m.id, "name": m.name, "category": m.category,
            "description": m.description, "workflow": m.workflow,
            "validation_status": m.validation_status,
            "validation_evidence": m.validation_evidence, "version": m.version,
            "parent_id": m.parent_id, "created_at": m.created_at.isoformat()}


# --- context graph (FalkorDB) ------------------------------------------------

@router.get("/context", summary="Context subgraph (FalkorDB) for the tenant")
def get_context(q: str = Query("", max_length=500),
                limit: int = Query(12, ge=1, le=50),
                user: CurrentUser = Depends(get_current_user)) -> dict:
    """Tenant-scoped research-context property graph.

    `available:false == graph disabled or unreachable -> reason says why;
    the empty lists mean "absent graph", NOT "no prior context". `q` is
    optional keyword filtering (>=5-char words, matched case-insensitively).
    """
    from app.memory.context_graph import get_context_graph

    graph = get_context_graph()
    keywords = [w.lower() for w in q.split() if len(w) >= 5][:4] if q.strip() else []
    sub = graph.context_subgraph(tenant_id=user.tenant_id, keywords=keywords,
                                 limit=limit)
    return {**sub, "graph": graph.status()}