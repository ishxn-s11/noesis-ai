"""Typed shared research state with optimistic versioning."""
from pydantic import BaseModel, Field


class TaskNode(BaseModel):
    id: str
    agent: str
    depends_on: list[str] = []
    label: str = ""
    status: str = "pending"  # pending|ready|running|succeeded|failed|blocked
    summary: str = ""


class ResearchState(BaseModel):
    """Shared workspace: every mutation goes through save_session_state(),
    which uses optimistic version checks so concurrent agents cannot silently
    overwrite each other's contributions."""

    objective: str = ""
    domain: str = "celestial"
    hypothesis: str = ""
    research_question: str = ""
    assignments: dict[str, str] = {}  # task id -> agent name
    task_graph: list[TaskNode] = []
    datasets: list[dict] = []
    approved_parameters: dict = {}
    simulation_configs: dict = {}
    completed_analyses: list[dict] = []
    intermediate_results: dict = {}
    open_uncertainties: list[str] = []
    validation_decisions: list[dict] = []
    next_actions: list[str] = []
    provenance: dict = {}  # node -> evidence summary refs

    def node(self, node_id: str) -> TaskNode | None:
        for n in self.task_graph:
            if n.id == node_id:
                return n
        return None

    def mark(self, node_id: str, status: str, summary: str = "") -> None:
        node = self.node(node_id)
        if node:
            node.status = status
            if summary:
                node.summary = summary
