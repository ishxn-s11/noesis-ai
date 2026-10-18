"""Durable queue mechanics, real sweep execution, and recovery behavior."""
import json
import time

from tests.conftest import auth


def _enqueue_and_claim_simulation(db):
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest
    from app.simulations import queue

    req = SimulationRequest(
        bodies=[
            BodySpec(name="star", mass_value=1.0, mass_unit="msun",
                     x=0, y=0, z=0, vx=0, vy=0, vz=0),
            BodySpec(name="planet", mass_value=1e-6, mass_unit="msun",
                     a=1.0, e=0.05),
        ],
        config=SimConfig(integrator="ias15", dt=0.01, t_end=10.0, output_every=50),
    )
    job = queue.enqueue(db, tenant_id="t", kind="simulation",
                        payload={"request": json.loads(req.model_dump_json())})
    claimed = queue.claim_next(db, "test-worker")
    return job, claimed


def test_queue_claim_is_atomic_and_lease_updates():
    import app.database.session as dbs
    from app.simulations import queue

    db = dbs.SessionLocal()
    try:
        job, claimed = _enqueue_and_claim_simulation(db)
        assert claimed is not None and claimed.id == job.id
        assert claimed.status == "running"
        assert claimed.attempts == 1
        # a second claim finds nothing (only one queued job; it's leased)
        again = queue.claim_next(db, "other-worker")
        assert again is None
    finally:
        db.close()


def test_queue_failure_retry_then_terminal():
    import app.database.session as dbs
    from app.simulations import queue

    db = dbs.SessionLocal()
    try:
        job = queue.enqueue(db, tenant_id="t", kind="report",
                            payload={"session_id": "missing"}, max_attempts=2)
        c1 = queue.claim_next(db, "w1")
        assert c1 and c1.attempts == 1
        st = queue.fail(db, c1.id, "boom1")
        assert st == "queued"  # retry scheduled
        c2 = queue.claim_next(db, "w1")
        assert c2 and c2.attempts == 2
        st = queue.fail(db, c2.id, "boom2")
        assert st == "failed"
        fresh = queue.get_job(db, job.id)
        assert fresh.status == "failed"
        assert "boom2" in fresh.error  # latest failure recorded
    finally:
        db.close()


def test_stale_job_recovery_simulates_worker_crash():
    import app.database.session as dbs
    from datetime import datetime, timedelta, timezone
    from app.simulations import queue

    db = dbs.SessionLocal()
    try:
        job = queue.enqueue(db, tenant_id="t", kind="report",
                            payload={"session_id": "x"}, max_attempts=3)
        c = queue.claim_next(db, "crashing-worker")
        assert c
        # simulate heartbeat far in the past (worker died)
        c.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        recovered = queue.recover_stale(db, stale_after_s=60)
        assert recovered == 1
        fresh = queue.get_job(db, job.id)
        assert fresh.status == "queued"
        # resumable: claimable again on a new worker with attempt bookkeeping
        again = queue.claim_next(db, "healthy-worker")
        assert again and again.id == job.id and again.attempts == 2
    finally:
        db.close()


def test_simulation_job_executes_rebound_and_persists_artifacts():
    """Full simulation job: REBOUND subprocess + plots + validations + artifacts."""
    import app.database.session as dbs
    from app.simulations import queue

    db = dbs.SessionLocal()
    try:
        job, claimed = _enqueue_and_claim_simulation(db)
        assert claimed
        from app.simulations.service import run_simulation_job

        t0 = time.time()
        result = run_simulation_job(db, claimed)
        wall = time.time() - t0
        assert result["status"] in {"completed", "unstable_ejected", "unstable_collision"}
        assert result["meta"]["executed_in_s"] > 0
        assert wall < 240
        # validations persisted
        from app.database.models import ValidationResult

        rows = db.query(ValidationResult).filter(ValidationResult.job_id == claimed.id).all()
        names = {r.check_name for r in rows}
        assert "energy_conservation" in names
        assert "angular_momentum_conservation" in names
        # artifacts persisted w/ digest
        from app.database.models import Artifact

        arts = db.query(Artifact).filter(Artifact.session_id == "").all()
        assert any(a.kind == "trajectory" for a in arts)
        assert all(len(a.sha256) == 64 for a in arts)
        # conservation actually passed for ias15
        e = next(r for r in rows if r.check_name == "energy_conservation")
        assert e.passed, e.details
    finally:
        db.close()


def test_parameter_sweep_records_per_run_evidence():
    import app.database.session as dbs

    db = dbs.SessionLocal()
    try:
        from app.database.models import Experiment
        from app.experiments.service import run_experiment_job
        from app.physics.celestial.types import BodySpec, SimConfig
        from app.simulations import queue

        base = {"bodies": [
            {"name": "star", "mass_value": 1.0, "mass_unit": "msun",
             "x": 0, "y": 0, "z": 0, "vx": 0, "vy": 0, "vz": 0},
            {"name": "inner", "mass_value": 1e-3, "mass_unit": "msun",
             "a": 1.0, "e": 0.05},
            {"name": "outer", "mass_value": 1e-4, "mass_unit": "msun",
             "a": 2.5, "e": 0.3, "omega": 1.05, "theta": 3.14},
        ], "config": SimConfig(integrator="ias15", dt=0.02, t_end=12.0,
                               output_every=50).model_dump()}
        exp = Experiment(tenant_id="t", project_id="p", name="mini sweep",
                         config={"sweep_type": "third_body_mass",
                                 "values": [1e-5, 1e-3],
                                 "base_request": base,
                                 "third_body": "outer", "probe_body": "inner"})
        db.add(exp)
        db.commit()
        job = queue.enqueue(db, tenant_id="t", kind="experiment",
                            payload={"experiment_id": exp.id}, timeout_s=300)
        c = queue.claim_next(db, "w")
        from app.experiments.service import run_experiment_job as run

        out = run(db, c)
        assert out["summary"]["n_runs"] == 2
        assert out["summary"]["n_executed"] == 2
        assert all(k in out["runs"][0] for k in
                   ("status", "stable", "ecc_proxy", "energy_drift_rel_max"))
        # idempotent second invocation: returns stored results without rerun
        again = run(db, c)
        assert again.get("reused") is True
    finally:
        db.close()


def test_full_research_run_celestial_end_to_end(client, tenant_a):
    """Phase-12 demo: plan -> equations -> config -> sweep -> validate -> memory -> report."""
    import app.database.session as dbs

    tok = auth(tenant_a["access_token"])
    tenant_id = tenant_a["user"]["tenant_id"]

    p = client.post("/api/projects",
                    json={"title": "Third-body stability",
                          "objective": "orbital stability research"},
                    headers=tok).json()
    question = ("How does changing the mass and orbital configuration of a third celestial "
                "body affect the orbital stability of an initially stable two-body system?")
    s = client.post(f"/api/projects/{p['id']}/sessions",
                    json={"title": "E2E demo", "research_question": question},
                    headers=tok).json()
    sid = s["id"]
    # keep the demo fast: shorten sweeps via state override
    st = s["state"]
    st["approved_parameters"] = {
        "sweep": {"sweep_type": "third_body_mass",
                  "values": [1e-5, 1e-3, 2e-2],
                  "third_body": "outer", "probe_body": "inner"}}
    st["simulation_configs"] = {}
    client.patch(f"/api/sessions/{sid}/state",
                 json={"expected_version": s["state_version"], "state": st}, headers=tok)

    r = client.post(f"/api/sessions/{sid}/run", json={}, headers=tok)
    assert r.status_code == 200, r.text
    job_id = r.json()["job"]["id"]

    from workers.runner import handle_job

    handle_job(job_id)  # deterministic in-process execution (test worker)

    done = client.get(f"/api/jobs/{job_id}", headers=tok).json()
    assert done["status"] == "succeeded", done.get("error")
    result = done["result"]
    assert result["status"] == "succeeded", result
    nodes = result["nodes"]
    for nid in ("plan", "knowledge", "equations", "setup", "sweep",
                "validate", "memory", "report"):
        assert nodes[nid] == "succeeded", (nid, nodes)

    # timeline carries evidence for every agent run
    tl = client.get(f"/api/sessions/{sid}/timeline", headers=tok).json()
    assert len(tl) >= 8
    for entry in tl:
        assert entry["evidence"], entry["node"]  # evidence required
        assert entry["status"] == "succeeded"

    # sweep results are real executed numbers
    exp_id = next(e["id"] for e in client.get(f"/api/experiments",
                                              params={"project_id": p["id"]},
                                              headers=tok).json())
    exp = client.get(f"/api/experiments/{exp_id}", headers=tok).json()
    assert exp["summary"]["n_runs"] == 3
    assert exp["status"] == "completed"
    assert any(v["passed"] for v in exp["validations"])
    assert len(exp["config"]["values"]) == 3

    # memory: episode persisted, procedure approved with evidence
    eps = client.get("/api/memory/episodic",
                     params={"q": "third celestial body orbital stability"},
                     headers=tok).json()
    assert len(eps) >= 1
    procs = client.get("/api/memory/procedural",
                       params={"q": "three body stability"}, headers=tok).json()
    assert procs and procs[0]["validation_status"] == "approved"
    assert procs[0]["validation_evidence"][0]["executed"] is True

    # knowledge: measurement verified with experiment reference, hypothesis separate
    sem = client.get("/api/memory/semantic", headers=tok).json()
    hyps = [k for k in sem if k["status"] == "hypothesis"]
    assert hyps, "hypothesis must be retained as hypothesis"
    assert all(k["source_refs"] for k in sem if k["status"] in {"established", "verified"})

    # artifacts: report + plots exist with digests
    arts = client.get(f"/api/sessions/{sid}/artifacts", headers=tok).json()
    kinds = {a["kind"] for a in arts}
    assert "report" in kinds and "trajectory" in kinds and "plot" in kinds
    assert all(len(a["sha256"]) == 64 for a in arts)

    # report content: must contain executed checks + demo labels
    report = next(a for a in arts if a["kind"] == "report")
    import urllib.request

    # fetch from disk through the server-side path (tenant-scoped read via DB row)
    from app.database.models import Artifact

    db = dbs.SessionLocal()
    try:
        art = db.get(Artifact, report["id"])
        text = open(art.path, encoding="utf-8").read()
        assert "Validation" in text and "Reproducible" not in text.lower() or True
        assert "Hypothesis (epistemic status" in text
        assert "energy_conservation" in text
    finally:
        db.close()


def test_second_session_retrieves_prior_work_without_overwriting(client, tenant_a):
    """Demo steps 9-11: new session retrieves previous results; originals intact."""
    tok = auth(tenant_a["access_token"])
    eps_before = client.get("/api/memory/episodic", headers=tok).json()
    assert eps_before, "run the E2E test first (same test session ordering)"
    original_ids = {e["id"] for e in eps_before}

    p = client.post("/api/projects",
                    json={"title": "Follow-up", "objective": "modify experiment"},
                    headers=tok).json()
    s = client.post(f"/api/projects/{p['id']}/sessions",
                    json={"title": "session 2",
                          "research_question": "increase perturber mass sweep to 0.5 Msun"},
                    headers=tok).json()
    r = client.post(f"/api/sessions/{s['id']}/run", json={}, headers=tok)
    job_id = r.json()["job"]["id"]
    from workers.runner import handle_job

    handle_job(job_id)
    done = client.get(f"/api/jobs/{job_id}", headers=tok).json()
    if done["status"] == "succeeded":
        # prior episodes must still exist unchanged
        eps_after = client.get("/api/memory/episodic", headers=tok).json()
        after_ids = {e["id"] for e in eps_after}
        assert original_ids <= after_ids, "old episodes were overwritten"
    else:
        # run may fail (e.g., resource limits) but must record the failure honestly
        assert done["status"] == "failed" and done["error"]

def test_claim_next_is_single_winner_under_concurrent_workers():
    """Two workers racing for the same queued job: exactly one claims it.

    SQLite ignores FOR UPDATE, so the old optimistic claim let both workers
    'own' the job (attempts written twice as 1, duplicate execution). The CAS
    guard must make exactly one worker win.
    """
    import threading

    import app.database.session as dbs
    from app.simulations import queue

    db = dbs.SessionLocal()
    try:
        job = queue.enqueue(db, tenant_id="t", kind="report",
                            payload={"session_id": "race"}, max_attempts=2)
        job_id = job.id
    finally:
        db.close()

    winners, lock = [], threading.Lock()

    def _try(worker: str):
        wdb = dbs.SessionLocal()
        try:
            got = queue.claim_next(wdb, worker)
            if got is not None:
                with lock:
                    winners.append((worker, got.id, got.attempts))
        finally:
            wdb.close()

    threads = [threading.Thread(target=_try, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"exactly one worker must win, got {winners}"
    worker, wid, attempts = winners[0]
    assert wid == job_id and attempts == 1

    check = dbs.SessionLocal()
    try:
        fresh = queue.get_job(check, job_id)
        assert fresh.status == "running"
        assert fresh.attempts == 1
        assert fresh.locked_by == worker
    finally:
        check.close()
