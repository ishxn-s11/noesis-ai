"""Context layer (FalkorDB) tests.

Three tiers:
1. disabled / unreachable — graceful degradation, no exceptions, honest flags;
2. recording fake — the exact Cypher generated: tenant isolation, parameterized
   queries, endpoint-then-relationship MERGEs;
3. live FalkorDB — opt-in via NOESIS_GRAPHDB_LIVE_TEST_URL (real server, e.g.
   `docker run -p 6379:6379 falkordb/falkordb`); skipped otherwise.
"""
import os

import pytest

from app.memory.context_graph import ContextGraph, _parse_url

TENANT = "tenant-a"
OTHER = "tenant-b"


# --- tier 1: disabled / unreachable ------------------------------------------

def test_disabled_reports_not_enabled_and_no_writes():
    g = ContextGraph("")
    assert g.status() == {"enabled": False, "available": False,
                          "reason": "NOESIS_GRAPHDB_URL not set"}
    assert g.context_subgraph(TENANT, ["stability"])["available"] is False
    assert g.upsert_node("Episode", "e1", TENANT, {"objective": "x"}) is False
    assert g.link(TENANT, "Session", "s", "RECORDED", "Episode", "e") is False
    res = g.sync_run(tenant_id=TENANT, question_id="q", question_text="q?",
                     session_id="s", episode_id="e", objective="o")
    assert res["attempted"] == 0 and res["written"] == 0


def test_unreachable_server_degrades_without_raising():
    g = ContextGraph("127.0.0.1:1", connect_timeout_s=0.5)
    st = g.status()
    assert st["enabled"] is True and st["available"] is False
    assert st["reason"] and st["reason"] != "not connected"
    sub = g.context_subgraph(TENANT, ["orbit"])
    assert sub["available"] is False and sub["nodes"] == []
    # backoff: a second call must not re-block on the connect timeout
    import time as _t
    t0 = _t.monotonic()
    g.upsert_node("Episode", "e1", TENANT, {})
    assert _t.monotonic() - t0 < 0.4


def test_url_parsing_variants():
    assert _parse_url("localhost:6379") == ("localhost", 6379)
    assert _parse_url("redis://graphdb:6379/0") == ("graphdb", 6379)
    assert _parse_url("falkordb://x:6380") == ("x", 6380)
    assert _parse_url("plainhost") == ("plainhost", 6379)


# --- tier 2: recording fake ---------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeGraph:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.writes = []   # (cypher, params)
        self.reads = []    # (cypher, params)

    def query(self, cypher, params=None):
        self.writes.append((cypher, params or {}))
        return _FakeResult([["e1"]])

    def ro_query(self, cypher, params=None):
        self.reads.append((cypher, params or {}))
        return _FakeResult(self.rows)


def _fake_graph(g: ContextGraph, rows=None) -> _FakeGraph:
    fg = _FakeGraph(rows)
    g._graph = fg          # pretend connection already succeeded
    g._schema_done = True
    return fg


def test_writes_are_parameterized_and_tenant_scoped():
    g = ContextGraph("localhost:6379")
    fg = _fake_graph(g)
    assert g.upsert_node("Episode", "ep1", TENANT, {"objective": "seen"}) is True
    cypher, params = fg.writes[0]
    assert "tenant_id: $tenantId" in cypher and "$tenantId" in cypher
    assert params["tenantId"] == TENANT and params["id"] == "ep1"
    # no literal user strings interpolated into the query text
    assert "seen" not in cypher
    assert "ep1" not in cypher

    ok = g.link(TENANT, "Episode", "ep1", "PRODUCES", "Experiment", "ex1")
    cypher, params = fg.writes[1]
    assert ok is True
    # endpoint-then-relationship pattern (three separate MERGEs)
    assert cypher.count("MERGE") == 3
    assert "[r:PRODUCES]" in cypher
    assert params["aId"] == "ep1" and params["bId"] == "ex1"


def test_invalid_relationship_type_rejected():
    g = ContextGraph("localhost:6379")
    fg = _fake_graph(g)
    assert g.link(TENANT, "Episode", "a", "BAD REL {}) MATCH (n) DETACH DELETE n",  # no-op
                  "Experiment", "b") is False
    assert fg.writes == []


def test_unknown_label_rejected():
    g = ContextGraph("localhost:6379")
    fg = _fake_graph(g)
    assert g.upsert_node("NotALabel", "x", TENANT, {}) is False
    assert fg.writes == []


def test_sync_run_reports_partial_failures():
    g = ContextGraph("localhost:6379")
    fg = _fake_graph(g)
    res = g.sync_run(
        tenant_id=TENANT, question_id="q1", question_text="how stable?",
        session_id="s1", episode_id="ep1", objective="Investigate",
        procedure={"id": "p1", "name": "sweep", "status": "approved"},
        knowledge_ids=["k1"], experiment_id="ex1", validation_id="v1",
        artifact_ids=["a1"])
    assert res["attempted"] == res["written"] and res["attempted"] >= 10
    # every write carried the tenant binding
    assert all(p.get("tenantId") == TENANT for _, p in fg.writes)


def test_context_read_parses_rows_and_keeps_tenant_filter():
    g = ContextGraph("localhost:6379")
    rows = [
        ("Episode", "ep1", "Third-body sweep", "completed", "2026-10-17"),
        ("Procedure", "p1", "three_body_stability_sweep", "approved", "2026-10-16"),
    ]
    fg = _fake_graph(g, rows=rows)

    # call 1 -> keyword matches; call 2 -> edges; call 3 -> neighbor props
    def ro_query(cypher, params=None):
        fg.reads.append((cypher, params or {}))
        if len(fg.reads) == 1:
            return _FakeResult(rows)
        if len(fg.reads) == 2:
            return _FakeResult([("ep1", "TESTS", "q1", "Question", "how stable?")])
        return _FakeResult([("Question", "q1", "how stable?", "", "2026-10-17")])
    fg.ro_query = ro_query

    sub = g.context_subgraph(TENANT, ["stability"], limit=8)
    assert sub["available"] is True
    labels = [n["label"] for n in sub["nodes"]]
    # matches plus the one-hop expanded neighbor
    assert labels == ["Episode", "Procedure", "Question"]
    assert sub["nodes"][2].get("via") == "neighbor"
    assert sub["edges"][0]["type"] == "TESTS"
    node_cypher, node_params = fg.reads[0]
    assert node_params["tenantId"] == TENANT and "kw0" in node_params
    # tenant filter AND-grouped with keywords (isolation parenthesization)
    assert "WHERE n.tenant_id = $tenantId AND (" in node_cypher
    edge_cypher, edge_params = fg.reads[1]
    assert "a.tenant_id = $tenantId" in edge_cypher
    assert "b.tenant_id = $tenantId" in edge_cypher
    # neighbor expansion stays tenant-scoped and id-based
    nb_cypher, nb_params = fg.reads[2]
    assert "n.tenant_id = $tenantId" in nb_cypher and nb_params["nid0"] == "q1"


def test_neighbor_expansion_can_be_disabled():
    g = ContextGraph("localhost:6379")
    fg = _fake_graph(g)

    def ro_query(cypher, params=None):
        fg.reads.append((cypher, params or {}))
        if len(fg.reads) == 1:
            return _FakeResult([("Episode", "ep1", "Third-body sweep",
                                 "completed", "2026-10-17")])
        return _FakeResult([("ep1", "TESTS", "q1", "Question", "q")])
    fg.ro_query = ro_query

    sub = g.context_subgraph(TENANT, [], limit=8, expand_neighbors=False)
    assert sub["available"] is True and len(sub["nodes"]) == 1
    assert len(fg.reads) == 2  # no third (neighbor) query
    # without keywords there is no keyword WHERE clause
    assert "AND (" not in fg.reads[0][0]


# --- tier 3: live server (opt-in) ---------------------------------------------

LIVE_URL = os.environ.get("NOESIS_GRAPHDB_LIVE_TEST_URL", "")


@pytest.mark.skipif(not LIVE_URL, reason="set NOESIS_GRAPHDB_LIVE_TEST_URL "
                                         "(e.g. localhost:6379) with a running "
                                         "FalkorDB server")
def test_live_falkordb_roundtrip():
    import time
    import uuid

    g = ContextGraph(LIVE_URL, graph_name=f"noesis_test_{uuid.uuid4().hex[:8]}")
    t0 = time.monotonic()
    assert g.status()["available"] is True, "cannot reach live FalkorDB"
    tenant = f"t_{uuid.uuid4().hex[:8]}"
    res = g.sync_run(
        tenant_id=tenant, question_id="q1", question_text="live test?",
        session_id="s1", episode_id="ep1", objective="live roundtrip",
        procedure={"id": "p1", "name": "live_sweep", "status": "approved"},
        knowledge_ids=["k1"], experiment_id="ex1", validation_id="v1")
    assert res["written"] == res["attempted"] and res["attempted"] > 0

    sub = g.context_subgraph(tenant, keywords=["live"], limit=10)
    assert sub["available"] is True
    assert {n["label"] for n in sub["nodes"]} >= {"Episode", "Procedure"}
    assert any(e["type"] == "APPROVES" for e in sub["edges"])

    # tenant isolation on a live server: another tenant sees nothing
    other = g.context_subgraph(f"t_{uuid.uuid4().hex[:8]}", keywords=["live"])
    assert other["nodes"] == [] and other["edges"] == []
    assert time.monotonic() - t0 < 15