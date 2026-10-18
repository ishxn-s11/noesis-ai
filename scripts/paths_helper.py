"""Fetch a report artifact's text content for the demo script."""
import httpx


def report_text(artifact_id: str, token: str, base: str) -> str:
    """Download the report through the tenant-scoped artifact endpoint."""
    resp = httpx.get(
        f"{base.rstrip('/')}/api/artifacts/{artifact_id}/download",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.text