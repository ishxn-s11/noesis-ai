"""Durable graph-based orchestration (checkpointed, resumable, parallel).

Framework choice: a purpose-built durable task graph over the DB-backed job
queue rather than LangGraph — each node's completion is committed to
job.checkpoint before successors start, so a process restart resumes the
investigation exactly where it stopped (Phase 3 recovery requirement).
Independent nodes run concurrently in a thread pool; dependent nodes only run
after their dependencies *succeeded* (pending upstream failures block them).
"""
import logging
import threading
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.database.models import AgentRun, Job, ResearchSession
from app.orchestration import events
from app.orchestration.state import ResearchState

log = logging.getLogger("noesis.graph")


@dataclass
class NodeContext:
    db: Session
    job: Job
    session: ResearchSession
    state: ResearchState
    node_id: str
    agent: str
    checkpoint: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class GraphRunner:
    def __init__(
        self,
        db: Session,
        job: Job,
        session: ResearchSession,
        handlers: dict[str, Callable[[NodeContext], AgentResult]],
        max_workers: int = 4,
    ) -> None:
        self.db = db
        self.job = job
        self.session = session
        self.handlers = handlers
        self.max_workers = max_workers
        self.checkpoint: dict = dict(job.checkpoint or {})
        self.nodes: dict[str, dict] = dict(self.checkpoint.get("nodes", {}))
        self.state = ResearchState.model_validate(
            self.checkpoint.get("state") or session.state or {}
        )
        self._write_lock = threading.Lock()

    # --- checkpointing -----------------------------------------------------
    def _save_checkpoint(self) -> None:
        with self._write_lock:
            self.checkpoint = {
                "nodes": self.nodes,
                "state": self.state.model_dump(),
                "plan": self.checkpoint.get("plan", {}),
            }
            # job.checkpoint write is guarded by callers in the main thread
            self.job.checkpoint = self.checkpoint
            self.db.commit()

    def _publish(self, event_type: str, **payload) -> None:
        events.publish(self.job.id, {"type": event_type, "job_id": self.job.id, **payload})

    # --- planning ----------------------------------------------------------
    def _init_nodes(self, plan: dict) -> None:
        for node in plan["nodes"]:
            nid = node["id"]
            if nid not in self.nodes:
                self.nodes[nid] = {"status": "pending", "output": {}, "evidence": []}
        self.checkpoint["plan"] = plan
        payload = self.state.model_dump()
        payload["task_graph"] = [
            {"id": n["id"], "agent": n["agent"], "depends_on": n.get("depends_on", []),
             "label": n.get("label", n["id"]),
             "status": self.nodes[n["id"]]["status"]}
            for n in plan["nodes"]
        ]
        payload["assignments"] = {n["id"]: n["agent"] for n in plan["nodes"]}
        self.state = ResearchState.model_validate(payload)
        self._save_checkpoint()

    def _ready(self) -> list[str]:
        ready = []
        for nid, rec in self.nodes.items():
            if rec["status"] in {"succeeded", "running", "failed", "blocked"}:
                continue
            deps = next(
                (n.get("depends_on", []) for n in self.checkpoint["plan"]["nodes"]
                 if n["id"] == nid), []
            )
            statuses = [self.nodes[d]["status"] if d in self.nodes else "missing" for d in deps]
            if all(s == "succeeded" for s in statuses):
                ready.append(nid)
            elif any(s in {"failed", "blocked", "missing"} for s in statuses):
                rec["status"] = "blocked"
                self.state.mark(nid, "blocked", "upstream dependency failed")
        return ready

    # --- execution ---------------------------------------------------------
    def _execute_node(self, node_id: str) -> tuple[str, AgentResult | None, str | None]:
        node_spec = next(n for n in self.checkpoint["plan"]["nodes"] if n["id"] == node_id)
        agent = node_spec["agent"]
        handler = self.handlers.get(node_spec.get("handler", node_spec["id"]))
        if handler is None:
            return node_id, None, f"No handler registered for node '{node_id}'"
        spec_max_retries = int(node_spec.get("max_retries", 1))
        last_error = ""
        # Each node runs on its own thread => its own DB session. SQLite and
        # SQLAlchemy sessions are not thread-safe; concurrent writers rely on
        # WAL + busy_timeout for serializable outcome.
        from app.database.session import SessionLocal

        node_db = SessionLocal()
        try:
            run_row = AgentRun(
                tenant_id=self.job.tenant_id, job_id=self.job.id,
                session_id=self.session.id, agent=agent, node=node_id,
                status="running", input={"depends_on": node_spec.get("depends_on", [])},
            )
            node_db.add(run_row)
            node_db.commit()
            node_job = node_db.get(Job, self.job.id)
            node_session = node_db.get(ResearchSession, self.session.id)

            for attempt in range(1, spec_max_retries + 1):
                try:
                    ctx = NodeContext(db=node_db, job=node_job, session=node_session,
                                      state=self.state, node_id=node_id, agent=agent,
                                      checkpoint=self.checkpoint)
                    result = handler(ctx)
                    if not result.evidence:
                        raise RuntimeError(
                            "node produced no evidence — rejected (agents must prove tool execution)"
                        )
                    with self._write_lock:
                        from datetime import datetime, timezone

                        self.nodes[node_id] = {
                            "status": "succeeded", "output": result.output,
                            "evidence": result.evidence, "attempts": attempt,
                        }
                        self.state.mark(node_id, "succeeded", result.summary)
                        self.state.provenance[node_id] = [
                            {"tool": e.get("tool"), "artifacts": e.get("artifact_ids", [])}
                            for e in result.evidence
                        ]
                        run_row.status = "succeeded"
                        run_row.output = result.output
                        run_row.evidence = result.evidence
                        run_row.finished_at = datetime.now(timezone.utc)
                        node_db.commit()
                    self._publish("node_succeeded", node=node_id, agent=agent,
                                  summary=result.summary, evidence_count=len(result.evidence))
                    self._save_checkpoint()
                    return node_id, result, None
                except Exception as exc:
                    last_error = f"{exc}"
                    log.warning("node %s attempt %d failed: %s", node_id, attempt, exc,
                                exc_info=True)
                    node_db.rollback()
                    if attempt < spec_max_retries:
                        self._publish("node_retry", node=node_id, attempt=attempt + 1,
                                      error=str(exc))
            # exhausted retries
            with self._write_lock:
                from datetime import datetime, timezone

                self.nodes[node_id] = {"status": "failed", "output": {},
                                       "evidence": [], "error": last_error}
                self.state.mark(node_id, "failed", last_error[:300])
                run_row.status = "failed"
                run_row.error = last_error
                run_row.finished_at = datetime.now(timezone.utc)
                node_db.commit()
            self._publish("node_failed", node=node_id, agent=agent, error=last_error[:500])
            self._save_checkpoint()
            return node_id, None, last_error
        finally:
            node_db.close()

    def run(self, plan: dict) -> dict:
        """Execute the plan from checkpoint; returns summary dict."""
        if not self.nodes:
            self._init_nodes(plan)
        else:
            # ensure any new nodes from an extended plan exist
            self._init_nodes({**plan, "nodes": plan["nodes"]})

        errors: list[dict] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            in_flight = {}
            while True:
                ready = [n for n in self._ready() if self.nodes[n]["status"] == "pending"]
                for nid in ready:
                    self.nodes[nid]["status"] = "running"
                    fut = pool.submit(self._execute_node, nid)
                    in_flight[fut] = nid
                if not in_flight:
                    break
                done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
                for fut in done:
                    nid = in_flight.pop(fut)
                    _, _, err = fut.result()
                    if err:
                        errors.append({"node": nid, "error": err[:800]})

        # final state persistence with optimistic version check
        self._save_session_state()
        failed = [nid for nid, rec in self.nodes.items() if rec["status"] in {"failed", "blocked"}]
        summary = {
            "status": "succeeded" if not failed else "completed_with_failures",
            "nodes": {nid: rec["status"] for nid, rec in self.nodes.items()},
            "failed_nodes": failed,
            "errors": errors,
            "domain": self.state.domain,
            "objective": self.state.objective,
        }
        self._publish("graph_finished", summary=summary)
        return summary

    def _save_session_state(self) -> None:
        """Optimistic-concurrency write of shared state to the session row."""
        for _ in range(5):
            current_version = self.session.state_version
            expected = self.checkpoint.get("state_version", current_version)
            fresh = self.db.get(ResearchSession, self.session.id)
            if fresh.state_version != expected:
                # conflict: another writer advanced — reload & merge node statuses
                self.checkpoint["state_version"] = fresh.state_version
                incoming = ResearchState.model_validate(fresh.state or {})
                for nid, rec in self.nodes.items():
                    incoming.mark(nid, self.state.node(nid).status if self.state.node(nid) else "pending",
                                  self.state.node(nid).summary if self.state.node(nid) else "")
                merged = incoming.model_dump()
                for k, v in self.state.model_dump().items():
                    if k in {"task_graph", "provenance"} or not merged.get(k):
                        merged[k] = v
                self.state = ResearchState.model_validate(merged)
                continue
            fresh.state = self.state.model_dump()
            fresh.state_version = current_version + 1
            self.db.commit()
            self.session.state = fresh.state
            self.session.state_version = fresh.state_version
            self.checkpoint["state_version"] = fresh.state_version
            self._save_checkpoint()
            return
