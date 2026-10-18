"""Research projects, sessions, messages, shared state, research runs (SSE)."""
import asyncio
import json

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import CurrentUser, get_current_user
from app.core.artifacts import artifact_public
from app.core.errors import NotFoundErr, ValidationErr
from app.database.models import (
    AgentRun,
    Artifact,
    Job,
    Message,
    ResearchProject,
    ResearchSession,
)
from app.database.session import get_db, set_tenant
from app.orchestration import events
from app.orchestration.handlers import DOMAINS, detect_domain
from app.orchestration.state import ResearchState
from app.simulations import queue

router = APIRouter(tags=["research"])


def _scoped_db(raw_db: Session, user: CurrentUser) -> Session:
    set_tenant(raw_db, user.tenant_id)
    return raw_db


class ProjectIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    objective: str = ""
    domain: str = ""


@router.post("/projects")
def create_project(body: ProjectIn, user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    domain = body.domain or detect_domain(body.objective or body.title)
    project = ResearchProject(tenant_id=user.tenant_id, created_by=user.id,
                              title=body.title, objective=body.objective or body.title,
                              domain=domain)
    db.add(project)
    db.commit()
    return _project(project)


@router.get("/projects")
def list_projects(user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    db = _scoped_db(db, user)
    rows = db.query(ResearchProject).filter(
        ResearchProject.tenant_id == user.tenant_id
    ).order_by(ResearchProject.created_at.desc()).all()
    return [_project(p) for p in rows]


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    project = db.query(ResearchProject).filter(
        ResearchProject.id == project_id, ResearchProject.tenant_id == user.tenant_id
    ).first()
    if not project:
        raise NotFoundErr("Project not found")
    out = _project(project)
    sessions = db.query(ResearchSession).filter(
        ResearchSession.project_id == project_id
    ).order_by(ResearchSession.created_at).all()
    out["sessions"] = [_session_brief(s) for s in sessions]
    return out


class SessionIn(BaseModel):
    title: str = "Investigation"
    research_question: str = Field(min_length=5, max_length=4000)
    domain: str = ""


@router.post("/projects/{project_id}/sessions")
def create_session(project_id: str, body: SessionIn,
                   user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    project = db.query(ResearchProject).filter(
        ResearchProject.id == project_id, ResearchProject.tenant_id == user.tenant_id
    ).first()
    if not project:
        raise NotFoundErr("Project not found")
    domain = body.domain or project.domain or detect_domain(body.research_question)
    if domain not in DOMAINS:
        raise ValidationErr(f"Unknown domain: {domain}")
    state = ResearchState(objective=f"Investigate: {body.research_question}",
                          research_question=body.research_question, domain=domain)
    session = ResearchSession(tenant_id=user.tenant_id, project_id=project_id,
                              user_id=user.id, title=body.title,
                              state=state.model_dump(), state_version=0)
    db.add(session)
    db.commit()
    return _session(session)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    messages = db.query(Message).filter(Message.session_id == session_id).order_by(
        Message.created_at, Message.id
    ).all()
    out = _session(session)
    out["messages"] = [
        {"id": m.id, "role": m.role, "agent": m.agent, "content": m.content,
         "meta": m.meta, "created_at": m.created_at.isoformat()}
        for m in messages
    ]
    jobs = db.query(Job).filter(Job.session_id == session_id).order_by(
        Job.created_at.desc()
    ).limit(20).all()
    out["jobs"] = [_job(j) for j in jobs]
    return out


@router.patch("/sessions/{session_id}/state")
def update_state(session_id: str, body: dict, user: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    """Optimistic-concurrency update of shared research state."""
    db = _scoped_db(db, user)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    expected = body.get("expected_version", session.state_version)
    if expected != session.state_version:
        raise ValidationErr("State version conflict; reload and retry",
                            details={"current_version": session.state_version})
    merged = dict(session.state or {})
    merged.update(body.get("state") or {})
    session.state = merged
    session.state_version = session.state_version + 1
    db.commit()
    return _session(session)


class RunIn(BaseModel):
    research_question: str = Field(min_length=5, max_length=4000, default="")
    title: str = "Investigation"


class PaperAnalyzeIn(BaseModel):
    url: str = Field(min_length=8, max_length=500,
                     description="arXiv link (abs/pdf) or DOI link")
    title: str = "Paper interpretation"


@router.post("/labs/paper/analyze",
             summary="Paper link → durable interpretation run (ingest→extract→run→explain)")
def analyze_paper(body: PaperAnalyzeIn,
                  user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    """Validate the link synchronously (422 on unsupported formats), create a
    project + session in the 'paper' domain, and enqueue the orchestration job.
    The client streams progress via /jobs/{id}/events like any research run."""
    db = _scoped_db(db, user)
    from app.physics.paper.ingest import parse_paper_ref

    ref = parse_paper_ref(body.url)  # ValidationErr -> 422 with guidance

    project = ResearchProject(
        tenant_id=user.tenant_id, created_by=user.id,
        title=f"Paper: {ref['id']}",
        objective=f"Interpret paper {ref['url']} — extract claims, run engines, explain",
        domain="paper")
    db.add(project)
    db.commit()

    question = f"Interpret paper {ref['url']}"
    state = ResearchState(
        objective=f"Interpret paper {ref['url']}",
        research_question=question, domain="paper",
        approved_parameters={"paper_url": ref["url"], "paper_ref": ref})
    session = ResearchSession(
        tenant_id=user.tenant_id, project_id=project.id, user_id=user.id,
        title=body.title, state=state.model_dump(), state_version=0)
    db.add(session)
    db.commit()

    job = queue.enqueue(db, tenant_id=user.tenant_id, kind="research_run",
                        payload={"session_id": session.id, "question": question},
                        project_id=project.id, session_id=session.id,
                        timeout_s=1800, max_attempts=2)
    return {"job": _job(job), "session_id": session.id,
            "project_id": project.id, "ref": ref}


@router.post("/sessions/{session_id}/run", summary="Start (or resume) research run")
def start_run(session_id: str, body: RunIn, user: CurrentUser = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    state = dict(session.state or {})
    question = body.research_question or state.get("research_question") or ""
    if not question:
        raise ValidationErr("research_question required to start a run")
    state["research_question"] = question
    if state.get("domain") not in DOMAINS:
        state["domain"] = detect_domain(question)
    session.state = state
    db.commit()

    # cancel-free: enqueue a fresh research_run if none active
    active = db.query(Job).filter(Job.session_id == session_id,
                                  Job.status.in_(["queued", "running"])).first()
    if active:
        return {"job": _job(active), "reused": True}

    job = queue.enqueue(db, tenant_id=user.tenant_id, kind="research_run",
                        payload={"session_id": session_id, "question": question},
                        project_id=session.project_id, session_id=session_id,
                        timeout_s=1800, max_attempts=2)
    return {"job": _job(job), "reused": False}


@router.get("/sessions/{session_id}/timeline", summary="Agent activity timeline")
def timeline(session_id: str, user: CurrentUser = Depends(get_current_user),
             db: Session = Depends(get_db)) -> list[dict]:
    db = _scoped_db(db, user)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    runs = db.query(AgentRun).filter(AgentRun.session_id == session_id).order_by(
        AgentRun.started_at
    ).all()
    return [
        {"id": r.id, "agent": r.agent, "node": r.node, "status": r.status,
         "summary": (r.output or {}).get("summary", ""),
         "evidence": r.evidence, "error": r.error[:400],
         "started_at": r.started_at.isoformat() if r.started_at else None,
         "finished_at": r.finished_at.isoformat() if r.finished_at else None}
        for r in runs
    ]


@router.get("/sessions/{session_id}/artifacts")
def session_artifacts(session_id: str, user: CurrentUser = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> list[dict]:
    db = _scoped_db(db, user)
    session = db.query(ResearchSession).filter(
        ResearchSession.id == session_id, ResearchSession.tenant_id == user.tenant_id
    ).first()
    if not session:
        raise NotFoundErr("Session not found")
    rows = db.query(Artifact).filter(Artifact.session_id == session_id).order_by(
        Artifact.created_at.desc()
    ).all()
    return [artifact_public(a) for a in rows]


@router.get("/artifacts/{artifact_id}/download", summary="Download artifact (tenant-scoped)")
def download_artifact(artifact_id: str, user: CurrentUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    db = _scoped_db(db, user)
    art = db.query(Artifact).filter(
        Artifact.id == artifact_id, Artifact.tenant_id == user.tenant_id
    ).first()
    if not art:
        raise NotFoundErr("Artifact not found")
    from pathlib import Path

    if not Path(art.path).exists():
        raise NotFoundErr("Artifact file missing from storage")
    return FileResponse(art.path, media_type=art.content_type, filename=art.filename)


@router.get("/jobs/{job_id}", summary="Job status (polling alternative to SSE)")
def job_status(job_id: str, user: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    db = _scoped_db(db, user)
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == user.tenant_id).first()
    if not job:
        raise NotFoundErr("Job not found")
    return _job(job)


@router.get("/jobs/{job_id}/events", summary="Live agent activity (SSE)")
async def job_events(job_id: str, user: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> StreamingResponse:
    db = _scoped_db(db, user)
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == user.tenant_id).first()
    if not job:
        raise NotFoundErr("Job not found")

    q = events.subscribe(job_id)

    def _blocking_get() -> dict | None:
        import queue as _queue

        try:
            return q.get(True, 1.0)
        except _queue.Empty:
            return None

    async def gen():
        try:
            # replay current status first
            fresh = db.query(Job).filter(Job.id == job_id).first()
            yield _sse({"type": "status", "status": fresh.status,
                        "checkpoint": fresh.checkpoint})
            idle = 0.0
            while True:
                evt = await asyncio.to_thread(_blocking_get)
                if evt is not None:
                    idle = 0.0
                    yield _sse(evt)
                    if evt.get("type") == "graph_finished":
                        break
                    continue
                idle += 1.0
                fresh = db.query(Job).filter(Job.id == job_id).first()
                yield _sse({"type": "ping", "job_status": fresh.status})
                if fresh.status in {"succeeded", "failed", "cancelled"} and idle > 2:
                    yield _sse({"type": "status", "status": fresh.status,
                                "checkpoint": fresh.checkpoint})
                    break
                if idle > 3600:
                    break
        finally:
            events.unsubscribe(job_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# --- helpers ---------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _project(p: ResearchProject) -> dict:
    return {"id": p.id, "title": p.title, "objective": p.objective, "domain": p.domain,
            "status": p.status, "created_at": p.created_at.isoformat(),
            "created_by": p.created_by}


def _session_brief(s: ResearchSession) -> dict:
    return {"id": s.id, "title": s.title, "status": s.status,
            "state_version": s.state_version,
            "created_at": s.created_at.isoformat()}


def _session(s: ResearchSession) -> dict:
    out = _session_brief(s)
    out.update({"project_id": s.project_id, "state": s.state, "summary": s.summary})
    return out


def _job(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts,
            "max_attempts": j.max_attempts, "error": j.error[:400],
            "result": j.result if j.status == "succeeded" else _light(j.result),
            "checkpoint": j.checkpoint, "project_id": j.project_id,
            "session_id": j.session_id,
            "created_at": j.created_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def _light(result: dict) -> dict:
    return {"keys": sorted((result or {}).keys())[:12]}