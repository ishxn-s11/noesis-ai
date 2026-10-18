"""Persistence and tenant boundaries for the disk-free backend."""
from unittest.mock import patch

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
