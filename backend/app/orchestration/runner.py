"""research_run job handler: build/resume graph and execute to completion."""
import logging

from sqlalchemy.orm import Session

from app.database.models import Job, ResearchSession
from app.orchestration.graph import GraphRunner
from app.orchestration.handlers import HANDLERS, detect_domain
from app.orchestration import events

log = logging.getLogger("noesis.runner")


def run_research_job(db: Session, job: Job) -> dict:
    session = db.get(ResearchSession, job.payload.get("session_id"))
    if session is None:
        raise RuntimeError(f"research session {job.payload.get('session_id')} not found")

    checkpoint = job.checkpoint or {}
    saved_plan = checkpoint.get("plan")
    if saved_plan and saved_plan.get("nodes"):
        plan = saved_plan  # resume: reuse exact plan from checkpoint
    else:
        question = (session.state or {}).get("research_question", "") or ""
        if not question:
            raise RuntimeError("session has no research_question in state")
        domain = (session.state or {}).get("domain") or detect_domain(question)
        from app.orchestration.handlers import DOMAINS

        plan = {"domain": domain, "nodes": DOMAINS[domain], "question": question}

    events.publish(job.id, {"type": "graph_started", "job_id": job.id,
                             "domain": plan.get("domain"),
                             "resumed": bool(checkpoint.get("nodes"))})
    runner = GraphRunner(db=db, job=job, session=session, handlers=HANDLERS)
    summary = runner.run(plan)
    return summary
