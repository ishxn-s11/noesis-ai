"""Persistence and tenant boundaries for the disk-free backend."""
from unittest.mock import patch
import pytest

from tests.conftest import auth


def test_database_artifact_survives_without_local_file(client, tenant_a, tenant_b, monkeypatch):
    from app.core.config import settings
    from app.core.artifacts import save_artifact
    from app.database.session import SessionLocal
    monkeypatch.setattr(settings, "artifact_storage", "database")
    with SessionLocal() as db:
        artifact = save_artifact(db, tenant_id=tenant_a["user"]["tenant_id"],
                                 kind="report", filename="report.txt", content=b"persisted science")
        artifact_id = artifact.id
        assert artifact.path.startswith("database:")
    path = f"/api/artifacts/{artifact_id}/download"
    response = client.get(path, headers=auth(tenant_a["access_token"]))
    assert response.status_code == 200
    assert response.content == b"persisted science"
    assert client.get(path, headers=auth(tenant_b["access_token"])).status_code == 404


def test_request_worker_cannot_execute_another_tenants_job(client, tenant_a, tenant_b, monkeypatch):
    from app.core.config import settings
    from app.database.session import SessionLocal
    from app.simulations.queue import enqueue
    monkeypatch.setattr(settings, "serverless", True)
    with SessionLocal() as db:
        job = enqueue(db, tenant_id=tenant_a["user"]["tenant_id"], kind="report", payload={})
        job_id = job.id
    with patch("subprocess.run") as run:
        response = client.post(f"/api/jobs/{job_id}/execute", headers=auth(tenant_b["access_token"]))
    assert response.status_code == 404
    run.assert_not_called()


def test_request_timeout_is_a_persisted_failure(client, tenant_a, monkeypatch):
    import subprocess
    from app.core.config import settings
    from app.database.session import SessionLocal
    from app.simulations.queue import enqueue
    monkeypatch.setattr(settings, "serverless", True)
    with SessionLocal() as db:
        job = enqueue(db, tenant_id=tenant_a["user"]["tenant_id"], kind="report", payload={})
        job_id = job.id
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 240)):
        response = client.post(f"/api/jobs/{job_id}/execute", headers=auth(tenant_a["access_token"]))
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_stellar_research_finishes_with_database_report(client, tenant_a, monkeypatch):
    pytest.importorskip("astropy", reason="Full research test requires the deployed scientific dependencies")
    from app.core.config import settings
    from app.database.session import SessionLocal
    from app.simulations.queue import enqueue
    from app.orchestration.runner import run_research_job
    monkeypatch.setattr(settings, "artifact_storage", "database")
    monkeypatch.setattr(settings, "graphdb_url", "")
    headers = auth(tenant_a["access_token"])
    project = client.post("/api/projects", headers=headers, json={
        "title": "Stellar deployment regression", "domain": "stellar",
    }).json()
    session = client.post(f"/api/projects/{project['id']}/sessions", headers=headers, json={
        "domain": "stellar", "research_question": "Estimate a solar mass main sequence star's luminosity and temperature.",
    }).json()
    with SessionLocal() as db:
        job = enqueue(db, tenant_id=tenant_a["user"]["tenant_id"], kind="research_run",
                      payload={"session_id": session["id"]}, project_id=project["id"], session_id=session["id"])
        result = run_research_job(db, job)
    assert result["status"] == "succeeded", result
    artifacts = client.get(f"/api/sessions/{session['id']}/artifacts", headers=headers).json()
    assert any(artifact["kind"] == "report" for artifact in artifacts)
