"""API integration tests: auth, RBAC-ish tenant isolation, memory semantics."""
import pytest

from tests.conftest import auth


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_register_login_and_me(client, tenant_a):
    assert tenant_a["user"]["role"] == "admin"  # first user in tenant
    r = client.get("/api/auth/me", headers=auth(tenant_a["access_token"]))
    assert r.status_code == 200
    assert r.json()["tenant_id"] == tenant_a["user"]["tenant_id"]


def test_login_wrong_password(client, tenant_a):
    r = client.post("/api/auth/login",
                    json={"email": "alice@noesis-lab.com", "password": "wrongpass1"})
    assert r.status_code == 401


def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/memory/episodic").status_code == 401
    assert client.get("/api/memory/semantic").status_code == 401


def test_tenant_isolation_of_projects_and_sessions(client, tenant_a, tenant_b):
    pa = client.post("/api/projects",
                     json={"title": "Lab A project", "objective": "orbit test"},
                     headers=auth(tenant_a["access_token"]))
    assert pa.status_code == 200
    pid = pa.json()["id"]

    # tenant B must not see or fetch tenant A's project
    lst = client.get("/api/projects", headers=auth(tenant_b["access_token"])).json()
    assert all(p["id"] != pid for p in lst)
    got = client.get(f"/api/projects/{pid}", headers=auth(tenant_b["access_token"]))
    assert got.status_code == 404


def test_episodic_memory_isolation_and_persistence(client, tenant_a, tenant_b):
    import app.database.session as dbs
    from app.memory.episodic import list_episodes, record_episode

    db = dbs.SessionLocal()
    try:
        mem = record_episode(db, tenant_id=tenant_a["user"]["tenant_id"],
                             project_id="", session_id="",
                             objective="energy drift experiment",
                             parameters={"dt": 0.01},
                             results={"drift": 1e-9})
        mem_b = record_episode(db, tenant_id=tenant_b["user"]["tenant_id"],
                               project_id="", session_id="",
                               objective="energy drift experiment",
                               parameters={"dt": 0.01},
                               results={"drift": 1e-9})
        assert mem.id != mem_b.id  # same content, different tenant -> separate
        only_a = list_episodes(db, tenant_id=tenant_a["user"]["tenant_id"])
        assert all(m.id != mem_b.id for m in only_a)
        # idempotency within a tenant
        again = record_episode(db, tenant_id=tenant_a["user"]["tenant_id"],
                               project_id="", session_id="",
                               objective="energy drift experiment",
                               parameters={"dt": 0.01},
                               results={"drift": 1e-9})
        assert again.id == mem.id
    finally:
        db.close()


def test_semantic_requires_sources_for_established(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    bad = client.post("/api/memory/semantic",
                      json={"kind": "equation", "title": "Kepler", "content": "P^2=a^3",
                            "status": "established", "source_refs": []},
                      headers=tok)
    assert bad.status_code == 422
    good = client.post("/api/memory/semantic",
                       json={"kind": "equation", "title": "Kepler", "content": "P^2=a^3/M",
                             "status": "established",
                             "source_refs": ["Murray & Dermott 1999"]},
                       headers=tok)
    assert good.status_code == 200


def test_hypothesis_promotion_to_verified_requires_evidence(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    h = client.post("/api/memory/semantic",
                    json={"kind": "hypothesis", "title": "test hyp", "content": "c",
                          "status": "hypothesis"}, headers=tok)
    assert h.status_code == 200
    hid = h.json()["id"]
    denied = client.post(f"/api/memory/semantic/{hid}/promote",
                         json={"new_status": "verified", "evidence_refs": []},
                         headers=tok)
    assert denied.status_code == 422
    allowed = client.post(f"/api/memory/semantic/{hid}/promote",
                          json={"new_status": "verified",
                                "evidence_refs": ["experiment:abc"]},
                          headers=tok)
    assert allowed.status_code == 200
    assert allowed.json()["version"] == 2
    # original retains status hypothesis — no silent overwrite
    orig = client.get(f"/api/memory/semantic/{hid}", headers=tok).json()
    assert orig["status"] == "hypothesis"
    assert allowed.json()["parent_id"] == hid


def test_procedure_approval_requires_execution_evidence(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    p = client.post("/api/memory/procedural",
                    json={"name": "fits pipeline", "category": "fits",
                          "workflow": {"steps": ["load", "trim"]}},
                    headers=tok)
    assert p.status_code == 200
    pid = p.json()["id"]
    assert p.json()["validation_status"] == "pending"
    denied = client.post(f"/api/memory/procedural/{pid}/approve",
                         json={"evidence": {"executed": False}}, headers=tok)
    assert denied.status_code == 422
    ok = client.post(f"/api/memory/procedural/{pid}/approve",
                     json={"evidence": {"executed": True, "validated": True,
                                        "job_id": "j1"}}, headers=tok)
    assert ok.status_code == 200
    assert ok.json()["validation_status"] == "approved"


def test_agent_registry_lists_eleven_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()["agents"]
    names = {a["name"] for a in agents}
    expected = {"orchestrator", "knowledge", "math", "stellar", "celestial",
                "cosmology", "observation", "simulation", "validation",
                "memory_coordinator", "report"}
    assert names == expected
    for a in agents:
        assert a["system_prompt"] and a["tools"] and a["memory_policy"]


def test_state_version_conflict_detection(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    p = client.post("/api/projects",
                    json={"title": "state project", "objective": "x"},
                    headers=tok).json()
    s = client.post(f"/api/projects/{p['id']}/sessions",
                    json={"title": "s", "research_question": "how do orbits evolve?"},
                    headers=tok).json()
    sid = s["id"]
    v = s["state_version"]
    r1 = client.patch(f"/api/sessions/{sid}/state",
                      json={"expected_version": v, "state": {"hypothesis": "h1"}},
                      headers=tok)
    assert r1.status_code == 200
    assert r1.json()["state_version"] == v + 1
    r2 = client.patch(f"/api/sessions/{sid}/state",
                      json={"expected_version": v, "state": {"hypothesis": "stale write"}},
                      headers=tok)
    assert r2.status_code == 422  # conflict detected


def test_archive_arxiv_connector_returns_real_papers_or_reports_failure(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    r = client.post("/api/labs/archive",
                    json={"archive": "arxiv",
                          "params": {"query": "gravitational wave cosmology",
                                     "max_results": 2}},
                    headers=tok)
    if r.status_code == 200:
        papers = r.json()["papers"]
        assert len(papers) <= 2
        for p in papers:
            assert p["id"].startswith("http") and p["title"]
    else:
        # network-blocked environment: must surface an explicit error, never fabricate
        assert r.status_code == 400
        assert "failed" in r.json()["message"].lower() or "archive" in r.json()["message"].lower()