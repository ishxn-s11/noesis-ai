"""Agent registry + coordination-center data endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import list_agents
from app.auth.service import CurrentUser, get_current_user
from app.core.errors import NotFoundErr
from app.database.models import AgentRun, Job, ResearchSession
from app.database.session import get_db, set_tenant

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", summary="Agent definitions: prompts, tools, memory policy")
def agents() -> dict:
    return {"agents": list_agents(), "count": len(list_agents())}


@router.get("/runs/{session_id}", summary="Coordination graph for a session")
def session_runs(session_id: str, user: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    set_tenant(db, user.tenant_id)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    runs = db.query(AgentRun).filter(AgentRun.session_id == session_id).order_by(
        AgentRun.started_at
    ).all()
    edges = []
    state = session.state or {}
    tasks = state.get("task_graph") or []
    status_by_node = {t["id"]: t.get("status", "pending") for t in tasks if isinstance(t, dict)}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        for dep in t.get("depends_on", []):
            edges.append({"source": dep, "target": t["id"]})
    return {
        "session": {"id": session.id, "state_version": session.state_version,
                    "domain": state.get("domain"), "objective": state.get("objective")},
        "nodes": [
            {"id": t["id"], "agent": t.get("agent", ""),
             "label": t.get("label", t["id"]),
             "status": status_by_node.get(t["id"], "pending"),
             "depends_on": t.get("depends_on", [])}
            for t in tasks if isinstance(t, dict)
        ],
        "edges": edges,
        "runs": [
            {"id": r.id, "agent": r.agent, "node": r.node, "status": r.status,
             "evidence": r.evidence, "error": r.error[:300],
             "output": r.output,
             "started_at": r.started_at.isoformat() if r.started_at else None,
             "finished_at": r.finished_at.isoformat() if r.finished_at else None}
            for r in runs
        ],
    }