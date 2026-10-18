"""Live smoke test; creates an isolated test tenant without logging credentials."""
import secrets
import sys
import uuid

import httpx


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "https://noesis-ai-drab.vercel.app"
    with httpx.Client(base_url=base, timeout=280) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        assert request("GET", "/health").json()["database"] == "ok"
        print("Health/database: passed", flush=True)
        suffix = uuid.uuid4().hex[:10]
        email = f"deployment-check-{suffix}@example.com"
        password = secrets.token_urlsafe(24)
        account = request("POST", "/api/auth/register", json={
            "tenant_name": f"Deployment verification {suffix}", "email": email,
            "password": password, "full_name": "Deployment verification",
        }).json()
        login = request("POST", "/api/auth/login", json={"email": email, "password": password}).json()
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        assert request("GET", "/api/auth/me").json()["id"] == account["user"]["id"]
        print("Registration/login/identity: passed", flush=True)
        project = request("POST", "/api/projects", json={
            "title": "Deployment smoke test", "objective": "Verify persistent research", "domain": "celestial",
        }).json()
        assert any(row["id"] == project["id"] for row in request("GET", "/api/projects").json())
        print("Persistent project: passed", flush=True)
        queued = request("POST", "/api/simulations", json={"project_id": project["id"], "request": {
            "bodies": [
                {"name": "star", "mass_value": 1.0, "mass_unit": "msun", "x": 0, "y": 0, "z": 0, "vx": 0, "vy": 0, "vz": 0},
                {"name": "planet", "mass_value": 1e-6, "mass_unit": "msun", "a": 1.0, "e": 0.05},
            ], "config": {"integrator": "ias15", "dt": 0.01, "t_end": 1.0, "output_every": 10},
        }}).json()
        job = request("POST", f"/api/jobs/{queued['job_id']}/execute").json()
        if job["status"] != "succeeded":
            raise RuntimeError(f"Simulation status={job['status']}: {job.get('error', '')}")
        result = request("GET", f"/api/simulations/{queued['job_id']}/result").json()
        assert result["status"] == "succeeded"
        artifacts = result["result"]["artifacts"]
        stored = next(artifact for artifact in artifacts if artifact.get("id"))
        payload = request("GET", f"/api/artifacts/{stored['id']}/download").content
        assert len(payload) > 0
        print(f"REBOUND job and persistent artifact: passed ({len(payload)} bytes)", flush=True)
        session = request("POST", f"/api/projects/{project['id']}/sessions", json={
            "title": "Stellar research verification", "domain": "stellar",
            "research_question": "Estimate luminosity and temperature of a solar mass main sequence star and validate the stellar model.",
        }).json()
        run = request("POST", f"/api/sessions/{session['id']}/run", json={}).json()
        completed = request("POST", f"/api/jobs/{run['job']['id']}/execute").json()
        assert completed["status"] == "succeeded", completed.get("error")
        if completed.get("result", {}).get("status") == "completed_with_failures":
            raise RuntimeError(f"Research contained failed tasks: {completed['result']}")
        evidence = request("GET", f"/api/sessions/{session['id']}/artifacts").json()
        assert any(artifact["kind"] == "report" for artifact in evidence), evidence
        print("Complete stellar research and persistent report: passed", flush=True)
        print("Live API verification completed", flush=True)


if __name__ == "__main__":
    main()
