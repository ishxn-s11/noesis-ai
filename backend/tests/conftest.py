"""Pytest fixtures: isolated SQLite DB per test run, API client, auth headers."""
import os
import tempfile
from pathlib import Path

import pytest

# Configure test environment BEFORE importing the app
_TMP = Path(tempfile.mkdtemp(prefix="noesis_test_"))
os.environ["NOESIS_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["NOESIS_JWT_SECRET"] = "test-secret"
os.environ["NOESIS_ARTIFACT_ROOT"] = str(_TMP / "artifacts")
os.environ["NOESIS_LLM_BASE_URL"] = ""
os.environ["NOESIS_LLM_API_KEY"] = ""
os.environ["NOESIS_EMBEDDING_PROVIDER"] = "local"
os.environ["NOESIS_WORKERS_ENABLED"] = "false"  # tests drive workers deterministically

# Tables must exist even for tests that never touch the API client
from app.database.session import init_db  # noqa: E402

init_db()


def pytest_sessionstart(session):  # noqa: ARG001
    init_db()


@pytest.fixture(scope="session")
def app():
    from app.main import create_app
    from app.database.session import init_db

    init_db()
    application = create_app()
    return application


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        c._tmp = _TMP  # expose for artifact assertions
        yield c


@pytest.fixture()
def tenant_a(client):
    r = client.post("/api/auth/register", json={
        "tenant_name": "Lab A", "email": "alice@noesis-lab.com", "password": "password123",
        "full_name": "Alice"})
    if r.status_code == 409:  # already registered in an earlier test
        r = client.post("/api/auth/login",
                        json={"email": "alice@noesis-lab.com", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def tenant_b(client):
    r = client.post("/api/auth/register", json={
        "tenant_name": "Lab B", "email": "bob@noesis-lab.com", "password": "password123",
        "full_name": "Bob"})
    if r.status_code == 409:
        r = client.post("/api/auth/login",
                        json={"email": "bob@noesis-lab.com", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}