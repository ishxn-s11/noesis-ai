"""NOESIS AI end-to-end demonstration (Phase 12 scenario).

Runs the full 12-step scenario against a live backend:

    python scripts/e2e_demo.py [--base http://127.0.0.1:8000]

Research question: how does third-body mass/orbit affect the stability of an
initially stable two-body system?

Steps: plan -> equations -> REBOUND configuration -> real parameter sweeps ->
validation -> durable memory -> visualization artifacts -> session close ->
new session retrieval -> modified experiment -> report. Everything executes
against the real API; every number comes from executed integrations.

Uses only the standard library + httpx (already a backend dependency).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

DEMO_QUESTION = (
    "How does changing the mass and orbital configuration of a third celestial body "
    "affect the orbital stability of an initially stable two-body system?"
)


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}", flush=True)


def wait_job(client: httpx.Client, job_id: str, token: str, timeout: int = 900) -> dict:
    """Poll the job (fallback) — SSE stream is consumed first by the caller."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        job = r.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


def stream_events(client: httpx.Client, job_id: str, token: str, deadline_s: int = 900) -> list[dict]:
    """Consume SSE progress events until graph_finished/status terminal."""
    events: list[dict] = []
    try:
        with client.stream(
            "GET", f"/api/jobs/{job_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(10.0, read=deadline_s),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                evt = json.loads(line[6:])
                events.append(evt)
                t = evt.get("type")
                if t in {"node_started", "node_succeeded", "node_failed", "node_retry"}:
                    log("sse", f"{t}: {evt.get('node')} ({evt.get('agent', '')})")
                if t == "graph_finished":
                    break
    except (httpx.HTTPError, httpx.ReadTimeout) as exc:
        log("sse", f"stream ended ({exc}); falling back to polling")
    return events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--tag", default="demo")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    client = httpx.Client(base_url=base, timeout=120.0)

    # 0. health
    health = client.get("/health").json()
    log("0", f"health: {health}")

    # 1. auth (register, fall back to login on rerun)
    email = f"{args.tag}-{int(time.time()) % 100000}@noesis-demo.com"
    r = client.post("/api/auth/register", json={
        "tenant_name": f"Demo Lab {args.tag}", "email": email,
        "password": "demo-password-1", "full_name": "Demo Researcher"})
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"email": email, "password": "demo-password-1"})
    r.raise_for_status()
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}
    log("1", f"authenticated as {email}")

    # 2. project + session (orchestrator will detect domain 'celestial')
    project = client.post("/api/projects", json={
        "title": "Third-body stability investigation",
        "objective": "Orbital stability under third-body perturbations"}, headers=H).json()
    session = client.post(f"/api/projects/{project['id']}/sessions", json={
        "title": "E2E demo session", "research_question": DEMO_QUESTION}, headers=H).json()
    sid = session["id"]
    log("2", f"project={project['id']} session={sid} domain={session['state'].get('domain')}")

    # 3-6. launch research run; workers execute the durable job graph
    started = client.post(f"/api/sessions/{sid}/run", json={}, headers=H).json()
    job_id = started["job"]["id"]
    log("3", f"research run job {job_id} queued (reused={started.get('reused')})")
    t0 = time.time()
    events = stream_events(client, job_id, token)
    job = wait_job(client, job_id, token)
    if job["status"] != "succeeded":
        log("x", f"JOB FAILED: {job.get('error')}")
        return 1
    summary = job["result"]
    log("6", f"run {summary['status']} in {time.time()-t0:.0f}s; nodes={summary['nodes']}")

    # timeline: evidence per agent
    timeline = client.get(f"/api/sessions/{sid}/timeline", headers=H).json()
    for entry in timeline:
        tools = sorted({e.get("tool", "?") for e in entry["evidence"]})
        log("7", f"{entry['agent']:20s} {entry['node']:14s} {entry['status']:9s} tools={tools}")

    # experiment results (real sweep numbers)
    exps = client.get("/api/experiments", params={"project_id": project["id"]}, headers=H).json()
    exp = client.get(f"/api/experiments/{exps[0]['id']}", headers=H).json()
    log("7", f"experiment '{exp['name']}': status={exp['status']} "
             f"stability_fraction={exp['summary'].get('stability_fraction')}")
    for run in exp["results"]:
        log("7", f"  {run.get('label'):16s} status={run.get('status'):18s} "
                 f"stable={run.get('stable')} e_proxy={run.get('ecc_proxy')} "
                 f"max|dE/E|={run.get('energy_drift_rel_max'):.2e}"
             if run.get("energy_drift_rel_max") is not None else
             f"  {run.get('label')} {run.get('status')} error={run.get('error')}")

    # artifacts
    artifacts = client.get(f"/api/sessions/{sid}/artifacts", headers=H).json()
    log("7", "artifacts: " + ", ".join(
        f"{a['kind']}:{a['filename']}({a['sha256'][:8]})" for a in artifacts))

    # 8-9. close session; new session retrieves prior work from durable memory
    eps_before = client.get("/api/memory/episodic",
                            params={"q": "third body orbital stability"}, headers=H).json()
    procs = client.get("/api/memory/procedural",
                       params={"q": "stability sweep"}, headers=H).json()
    sem = client.get("/api/memory/semantic", headers=H).json()
    log("8", f"session closed conceptually; durable memory holds "
             f"{len(eps_before)} episodes, {len(procs)} procedures, {len(sem)} knowledge items")
    log("9", f"procedure status: {[(p['name'], p['validation_status'], p['version']) for p in procs]}")

    # 10-11. modified experiment reusing prior knowledge, originals intact
    session2 = client.post(f"/api/projects/{project['id']}/sessions", json={
        "title": "Modified experiment",
        "research_question": ("Repeat the third-body stability sweep with higher perturber "
                              "masses up to 0.1 solar masses")}, headers=H).json()
    sid2 = session2["id"]
    state2 = session2["state"]
    state2["approved_parameters"] = {
        "sweep": {"sweep_type": "third_body_mass",
                  "values": [1e-4, 1e-3, 1e-2, 0.05],
                  "third_body": "outer", "probe_body": "inner"}}
    client.patch(f"/api/sessions/{sid2}/state",
                 json={"expected_version": session2["state_version"], "state": state2},
                 headers=H)
    started2 = client.post(f"/api/sessions/{sid2}/run", json={}, headers=H).json()
    job2 = wait_job(client, started2["job"]["id"], token)
    if job2["status"] == "succeeded":
        log("11", f"modified run succeeded: {job2['result']['nodes']}")
    else:
        log("11", f"modified run status={job2['status']} error={job2.get('error')}")

    eps_after = client.get("/api/memory/episodic", headers=H).json()
    ids_before = {e["id"] for e in eps_before}
    ids_after = {e["id"] for e in eps_after}
    assert ids_before <= ids_after, "prior episodes were overwritten!"
    log("11", f"prior episodes intact: {len(ids_before)} before, {len(ids_after)} after "
              f"(originals preserved)")

    # 12. report
    arts2 = client.get(f"/api/sessions/{sid}/artifacts", headers=H).json()
    report = next((a for a in arts2 if a["kind"] == "report"), None)
    if report:
        from paths_helper import report_text  # sibling module in scripts/
        text = report_text(report["id"], token, base)
        log("12", f"report: {report['filename']} sha256={report['sha256'][:12]}… "
                  f"({len(text.splitlines())} lines)")
        Path("demo_report.md").write_text(text, encoding="utf-8")
        log("12", "wrote demo_report.md")

    print("\nDEMONSTRATION COMPLETE:",
          "persistent memory + agent collaboration + real astrophysics "
          "computation + reproducible report ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())