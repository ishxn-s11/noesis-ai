"""Context layer: FalkorDB property graph of research context.

FalkorDB (https://github.com/FalkorDB/FalkorDB) is an openCypher graph
database speaking the Redis protocol. It links the otherwise-row-shaped
memory systems into one traversable context subgraph that agents consult
before planning and that the memory coordinator writes after every run.

Schema (every node carries `tenant_id`; ALL queries filter on it):

    (:Question {tenant_id, id, text})
    (:Session  {tenant_id, id, title})
    (:Episode  {tenant_id, id, objective, status, created_at})
    (:Procedure{tenant_id, id, name, status, created_at})
    (:Knowledge{tenant_id, id, title, kind, status})
    (:Experiment {tenant_id, id, status})
    (:Validation {tenant_id, id, all_passed})
    (:Artifact  {tenant_id, id, filename, kind})

    (Session)-[:RECORDED]->(Episode)
    (Episode)-[:APPROVES|PENDING]->(Procedure)
    (Episode)-[:TESTS]->(Question)
    (Episode)-[:PRODUCES]->(Experiment)
    (Experiment)-[:VALIDATED_BY]->(Validation)
    (Knowledge)-[:SUPPORTED_BY]->(Experiment)

Design rules (from the FalkorDB docs):
- MERGE each endpoint separately, then MERGE the relationship — merging a
  whole path in one clause would duplicate endpoints.
- Parameterized queries only ($tenantId etc.), never string interpolation.
- Degradation: URL unset -> disabled; server unreachable -> every operation
  returns ok/available=False with a reason. Nothing in the API or agents may
  present graph data as retrieved when `available` is False, and run results
  are never blocked by the graph being down (relational memory is primary).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

log = logging.getLogger(__name__)

CTX_LABELS = (
    "Question", "Session", "Episode", "Procedure",
    "Knowledge", "Experiment", "Validation", "Artifact",
)

_NODE_MERGE = "MERGE (n:{label} {{id: $id, tenant_id: $tenantId}})"


def _scalar_props(props: dict[str, Any] | None) -> dict[str, Any]:
    """FalkorDB parameters must be scalars/lists — flatten and filter."""
    return {k: v for k, v in (props or {}).items()
            if isinstance(v, (str, int, float, bool))}


def _parse_url(url: str) -> tuple[str, int]:
    """Accept 'host:port', 'redis://host:port' or 'falkordb://host:port'."""
    m = re.match(r"^(?:redis|falkordb)://", url)
    if m:
        url = url[m.end():]
    url = url.split("/")[0]
    if ":" in url:
        host, _, port = url.rpartition(":")
        return host or "localhost", int(port)
    return url or "localhost", 6379


class ContextGraph:
    """Lazy, failure-tolerant handle to a FalkorDB graph."""

    def __init__(self, url: str, graph_name: str = "noesis",
                 password: str = "", connect_timeout_s: float = 2.0):
        self._url = url
        self._graph_name = graph_name
        self._password = password
        self._connect_timeout = connect_timeout_s
        self._graph = None
        self._schema_done = False
        self._last_error: str | None = None
        self._retry_after = 0.0  # monotonic deadline after a failed attempt

    # --- connection ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self._url)

    @property
    def available(self) -> bool:
        return self._graph is not None

    def _connect(self):
        """Return a graph handle or None; never raises."""
        if not self._url:
            return None
        if self._graph is not None:
            return self._graph
        if time.monotonic() < self._retry_after:
            return None  # recent failure: degrade fast instead of re-blocking
        try:
            from falkordb import FalkorDB

            host, port = _parse_url(self._url)
            db = FalkorDB(
                host=host, port=port,
                password=self._password or None,
                socket_connect_timeout=self._connect_timeout,
                socket_timeout=self._connect_timeout,
            )
            self._graph = db.select_graph(self._graph_name)
            self._ensure_schema()
            self._last_error = None
            log.info("context graph connected: %s (graph=%s)", self._url, self._graph_name)
        except Exception as exc:  # any connection/setup failure degrades
            self._graph = None
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._retry_after = time.monotonic() + max(5.0, 5 * self._connect_timeout)
            log.warning("context graph unavailable (%s): %s", self._url, self._last_error)
        return self._graph

    def _ensure_schema(self) -> None:
        if self._schema_done or self._graph is None:
            return
        for label in CTX_LABELS:
            try:
                self._graph.query(
                    f"CREATE INDEX FOR (n:{label}) ON (n.tenant_id)")
            except Exception:
                pass  # index may already exist / older syntax; MERGE still works
        self._schema_done = True

    def status(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "available": False,
                    "reason": "NOESIS_GRAPHDB_URL not set"}
        if self._graph is None and time.monotonic() >= self._retry_after:
            self._connect()  # one real attempt so the reason is accurate
        if self._graph is None:
            return {"enabled": True, "available": False,
                    "reason": self._last_error or "not connected"}
        return {"enabled": True, "available": True, "graph": self._graph_name,
                "server": self._url}

    # --- writes -------------------------------------------------------------
    def upsert_node(self, label: str, node_id: str, tenant_id: str,
                    props: dict[str, Any] | None = None) -> bool:
        """MERGE a single tenant-scoped node. Returns True when written."""
        graph = self._connect()
        if graph is None or label not in CTX_LABELS:
            return False
        # Per-property SET (no map-union syntax): every value is a bound
        # parameter; the Cypher text contains property names only.
        scalar = _scalar_props(props)
        params: dict[str, Any] = {"id": node_id, "tenantId": tenant_id}
        sets = []
        for key, val in scalar.items():
            params[f"p_{key}"] = val
            sets.append(f"n.{key} = $p_{key}")
        cypher = (
            _NODE_MERGE.format(label=label) + " " +
            "ON CREATE SET n.created_at = coalesce($createdAt, '') " +
            "ON MATCH SET n.updated_at = $updatedAt " +
            (("SET " + ", ".join(sets) + " ") if sets else "") +
            "RETURN n.id"
        )
        params["createdAt"] = scalar.get("created_at", "")
        params["updatedAt"] = scalar.get("updated_at", "")
        try:
            graph.query(cypher, params)
            return True
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            log.warning("context graph upsert failed: %s", self._last_error)
            return False

    def link(self, tenant_id: str,
             a_label: str, a_id: str, rel: str,
             b_label: str, b_id: str, props: dict[str, Any] | None = None) -> bool:
        """MERGE endpoints separately, then the relationship (FalkorDB guide)."""
        graph = self._connect()
        if graph is None or not re.fullmatch(r"[A-Z_]+", rel or ""):
            return False
        cypher = (
            f"MERGE (a:{a_label} {{id: $aId, tenant_id: $tenantId}}) "
            f"MERGE (b:{b_label} {{id: $bId, tenant_id: $tenantId}}) "
            f"MERGE (a)-[r:{rel}]->(b)"
        )
        params: dict[str, Any] = {
            "aId": a_id, "bId": b_id, "tenantId": tenant_id,
        }
        for key, val in _scalar_props(props).items():
            params[f"r_{key}"] = val
            cypher += f" SET r.{key} = $r_{key}"
        try:
            graph.query(cypher, params)
            return True
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            log.warning("context graph link failed: %s", self._last_error)
            return False

    def sync_run(self, *, tenant_id: str, question_id: str, question_text: str,
                 session_id: str, episode_id: str, objective: str,
                 procedure: dict | None = None, knowledge_ids: list[str] | None = None,
                 experiment_id: str | None = None, validation_id: str | None = None,
                 artifact_ids: list[str] | None = None) -> dict:
        """Write one completed research run into the context graph.

        Returns {"written": n, "attempted": m}; partial failures are reported,
        never silently swallowed.
        """
        graph = self._connect()
        if graph is None:
            return {"written": 0, "attempted": 0, **self.status()}
        written = attempted = 0

        def step(ok: bool) -> None:
            nonlocal written, attempted
            attempted += 1
            written += int(ok)

        step(self.upsert_node("Question", question_id, tenant_id,
                              {"text": question_text[:500]}))
        step(self.upsert_node("Session", session_id, tenant_id, {}))
        step(self.upsert_node("Episode", episode_id, tenant_id,
                              {"objective": objective[:500], "status": "completed"}))
        step(self.link(tenant_id, "Session", session_id, "RECORDED",
                       "Episode", episode_id))
        step(self.link(tenant_id, "Episode", episode_id, "TESTS",
                       "Question", question_id))
        if procedure:
            proc_id = procedure.get("id")
            status = procedure.get("status", "pending")
            step(self.upsert_node("Procedure", proc_id, tenant_id,
                                  {"name": procedure.get("name", "")[:200],
                                   "status": status}))
            step(self.link(tenant_id, "Episode", episode_id,
                           "APPROVES" if status == "approved" else "PENDING",
                           "Procedure", proc_id))
        if experiment_id:
            step(self.upsert_node("Experiment", experiment_id, tenant_id, {}))
            step(self.link(tenant_id, "Episode", episode_id, "PRODUCES",
                           "Experiment", experiment_id))
            if validation_id:
                step(self.upsert_node("Validation", validation_id, tenant_id, {}))
                step(self.link(tenant_id, "Experiment", experiment_id,
                               "VALIDATED_BY", "Validation", validation_id))
        for kid in knowledge_ids or []:
            step(self.upsert_node("Knowledge", kid, tenant_id, {}))
            if experiment_id:
                step(self.link(tenant_id, "Knowledge", kid, "SUPPORTED_BY",
                               "Experiment", experiment_id))
        for aid in artifact_ids or []:
            step(self.upsert_node("Artifact", aid, tenant_id, {}))
        return {"written": written, "attempted": attempted, **self.status()}

    # --- reads --------------------------------------------------------------
    def context_subgraph(self, tenant_id: str, keywords: list[str] | None = None,
                         limit: int = 12, edge_limit: int = 40,
                         expand_neighbors: bool = True) -> dict:
        """Retrieve the tenant's context subgraph, optionally keyword-filtered.

        When `expand_neighbors` is true, every node adjacent to a match is
        also returned as a full node (marked ``via: "neighbor"``) so callers
        see connected procedures, validations and experiments — not just the
        keyword hits. Expansion is exactly one hop and tenant-scoped like
        every other statement.

        Returns {"available", "nodes": [...], "edges": [...]} (plus "reason"
        when unavailable). Callers must not present an unavailable graph as an
        empty result: `available` is the honesty flag.
        """
        graph = self._connect()
        if graph is None:
            return {"available": False, "reason": self.status()["reason"],
                    "nodes": [], "edges": []}
        kw = [k.lower()[:40] for k in (keywords or []) if k.strip()][:6]
        try:
            # Conservative openCypher: tenant isolation is a parenthesized
            # top-level AND; keyword terms OR together inside it. Only
            # CONTAINS/coalesce are used (FalkorDB implements an openCypher
            # subset — no list predicates or map access).
            node_params: dict[str, Any] = {"tenantId": tenant_id,
                                           "limit": int(limit)}
            kw_clauses = []
            for i, term in enumerate(kw):
                kw_clauses.append(
                    "toLower(coalesce(n.title, n.name, n.objective, "
                    f"n.text, '')) CONTAINS $kw{i}")
                node_params[f"kw{i}"] = term
            node_cypher = "MATCH (n) WHERE n.tenant_id = $tenantId"
            if kw_clauses:
                node_cypher += " AND (" + " OR ".join(kw_clauses) + ")"
            node_cypher += (
                " RETURN labels(n)[0], n.id, "
                "coalesce(n.title, n.name, n.objective, n.text, ''), "
                "coalesce(n.status, ''), coalesce(n.created_at, '') "
                "LIMIT $limit")
            node_rows = graph.ro_query(node_cypher, node_params).result_set
            node_ids = [r[1] for r in node_rows]
            nodes = [{"label": r[0], "id": r[1], "title": str(r[2])[:160],
                      "status": r[3], "created_at": r[4]} for r in node_rows]
            if not node_ids:
                return {"available": True, "nodes": [], "edges": []}
            edge_cypher = "MATCH (a) WHERE a.tenant_id = $tenantId AND ("
            edge_params: dict[str, Any] = {
                "tenantId": tenant_id, "edgeLimit": int(edge_limit)}
            edge_cypher += " OR ".join(
                f"a.id = $id{i}" for i in range(len(node_ids))) + ") "
            for i, nid in enumerate(node_ids):
                edge_params[f"id{i}"] = nid
            edge_cypher += (
                "MATCH (a)-[r]-(b) WHERE b.tenant_id = $tenantId "
                "RETURN a.id, type(r), b.id, labels(b)[0], "
                "coalesce(b.title, b.name, b.objective, b.text, '') "
                "LIMIT $edgeLimit")
            edge_rows = graph.ro_query(edge_cypher, edge_params).result_set
            edges = [{"source": r[0], "type": r[1], "target": r[2],
                      "target_label": r[3], "target_title": str(r[4])[:160]}
                     for r in edge_rows]

            # One-hop enrichment: fetch full props for adjacent nodes that
            # were not keyword matches themselves.
            if expand_neighbors and edges:
                matched = set(node_ids)
                neighbor_ids: list[str] = []
                for r in edge_rows:
                    for nid in (r[0], r[2]):
                        if nid not in matched and nid not in neighbor_ids:
                            neighbor_ids.append(nid)
                if neighbor_ids:
                    nb_cypher = "MATCH (n) WHERE n.tenant_id = $tenantId AND ("
                    nb_cypher += " OR ".join(
                        f"n.id = $nid{i}" for i in range(len(neighbor_ids))) + ") "
                    nb_cypher += (
                        "RETURN labels(n)[0], n.id, "
                        "coalesce(n.title, n.name, n.objective, n.text, ''), "
                        "coalesce(n.status, ''), coalesce(n.created_at, '') "
                        "LIMIT $limit")
                    nb_params: dict[str, Any] = {
                        "tenantId": tenant_id, "limit": int(limit)}
                    for i, nid in enumerate(neighbor_ids):
                        nb_params[f"nid{i}"] = nid
                    for r in graph.ro_query(nb_cypher, nb_params).result_set:
                        nodes.append({"label": r[0], "id": r[1],
                                      "title": str(r[2])[:160], "status": r[3],
                                      "created_at": r[4], "via": "neighbor"})
            return {"available": True, "nodes": nodes, "edges": edges}
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            log.warning("context graph query failed: %s", self._last_error)
            return {"available": False, "reason": self._last_error,
                    "nodes": [], "edges": []}


_default: ContextGraph | None = None


def get_context_graph() -> ContextGraph:
    """Process-wide handle configured from settings (lazy singleton)."""
    global _default
    if _default is None:
        from app.core.config import settings

        _default = ContextGraph(
            settings.graphdb_url, settings.graphdb_graph,
            settings.graphdb_password, settings.graphdb_timeout_s,
        )
    return _default