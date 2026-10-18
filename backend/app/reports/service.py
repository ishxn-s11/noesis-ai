"""report job handler executed by workers."""
from app.database.models import Job, ResearchSession
from app.reports.generate import generate_report


def run_report_job(db, job: Job) -> dict:
    session = db.get(ResearchSession, job.payload.get("session_id"))
    if session is None:
        raise RuntimeError("session not found for report job")
    state_model = _state_from_session(session, job)
    art, summary = generate_report(db, job=job, session=session, state=state_model)
    return {"artifact_id": art.id, "filename": art.filename, **summary}


def _state_from_session(session, job: Job):
    from app.orchestration.state import ResearchState

    checkpoint_state = (job.checkpoint or {}).get("state")
    if checkpoint_state:
        return ResearchState.model_validate(checkpoint_state)
    return ResearchState.model_validate(session.state or {})