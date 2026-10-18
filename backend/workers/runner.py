"""Worker: polls the durable job queue and executes job handlers.

Run standalone:  python -m workers.runner
Also started with the API in development (NOESIS_WORKERS_ENABLED=true).

Recovery: on startup, stale running jobs (expired heartbeat) are requeued, so
a crashed worker never strands an investigation mid-run.
"""
import logging
import socket
import threading
import time
import traceback

from app.core.config import settings
from app.database.session import SessionLocal
from app.simulations import queue
from app.simulations.service import run_simulation_job

log = logging.getLogger("noesis.worker")

WORKER_ID = f"{socket.gethostname()}-{threading.get_ident():x}"


def handle_job(job_id: str) -> None:
    from app.experiments.service import run_experiment_job
    from app.reports.service import run_report_job
    from app.orchestration.runner import run_research_job

    db = SessionLocal()
    try:
        job = queue.get_job(db, job_id)
        if job is None:
            return
        queue.heartbeat(db, job.id)
        kind = job.kind
        if kind == "simulation":
            result = run_simulation_job(db, job)
        elif kind == "experiment":
            result = run_experiment_job(db, job)
        elif kind == "research_run":
            result = run_research_job(db, job)
        elif kind == "report":
            result = run_report_job(db, job)
        else:
            raise RuntimeError(f"No handler for job kind: {kind}")
        queue.complete(db, job.id, result)
        log.info("job %s (%s) succeeded", job.id, kind)
    except Exception as exc:
        log.error("job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
        db2 = SessionLocal()
        try:
            queue.fail(db2, job_id, f"{exc}")
        finally:
            db2.close()
    finally:
        db.close()


def worker_loop(stop_event: threading.Event, worker_id: str = WORKER_ID) -> None:
    recovered = 0
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            if recovered == 0:
                n = queue.recover_stale(db, settings.stale_job_heartbeat_s)
                if n:
                    log.warning("recovered %d stale job(s)", n)
                recovered = 1
            job = queue.claim_next(db, worker_id)
            if job is None:
                db.close()
                stop_event.wait(settings.worker_poll_interval_s)
                continue
            job_id, kind = job.id, job.kind
        finally:
            db.close()
        log.info("claimed job %s (%s)", job_id, kind)
        handle_job(job_id)


def start_workers(n: int | None = None) -> tuple[threading.Event, list[threading.Thread]]:
    """Start worker threads; returns (stop_event, threads) for lifespan shutdown."""
    stop_event = threading.Event()
    threads = []
    for i in range(n or settings.worker_count):
        t = threading.Thread(
            target=worker_loop, args=(stop_event,), name=f"noesis-worker-{i}", daemon=True
        )
        t.start()
        threads.append(t)
    return stop_event, threads


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from app.database.session import init_db

    init_db()
    stop_event, threads = start_workers()
    log.info("workers started: %d", len(threads))
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
