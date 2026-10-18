"""Artifact storage: scientific outputs on disk with DB provenance records.

Artifacts live under NOESIS_ARTIFACT_ROOT/<tenant_id>/<project_id>/ with a
SHA-256 digest recorded so results can be verified after the fact.
"""
import hashlib
import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Artifact, ArtifactContent


def _root() -> Path:
    p = Path(settings.artifact_root).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_artifact(
    db: Session,
    *,
    tenant_id: str,
    kind: str,
    filename: str,
    content: bytes,
    project_id: str = "",
    session_id: str = "",
    content_type: str = "application/octet-stream",
    meta: dict | None = None,
) -> Artifact:
    rel_dir = Path(tenant_id) / (project_id or "global")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    artifact_id = str(uuid.uuid4())
    if settings.artifact_storage == "database":
        # Keep responses below Vercel's 4.5 MB payload limit.
        if len(content) > 4_000_000:
            raise ValueError("Artifact exceeds the free deployment's 4 MB limit")
        path = f"database:{artifact_id}"
        db.add(ArtifactContent(artifact_id=artifact_id, content=content))
    else:
        abs_dir = _root() / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        path = abs_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        path.write_bytes(content)
    art = Artifact(
        id=artifact_id,
        tenant_id=tenant_id,
        project_id=project_id,
        session_id=session_id,
        kind=kind,
        filename=safe_name,
        path=str(path),
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        meta=meta or {},
    )
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


def save_json_artifact(db: Session, *, tenant_id: str, kind: str, filename: str,
                       payload: dict, **kwargs) -> Artifact:
    return save_artifact(
        db, tenant_id=tenant_id, kind=kind, filename=filename,
        content=json.dumps(payload, indent=2, default=str).encode(),
        content_type="application/json", **kwargs,
    )


def artifact_public(art: Artifact) -> dict:
    return {
        "id": art.id, "kind": art.kind, "filename": art.filename,
        "content_type": art.content_type, "size_bytes": art.size_bytes,
        "sha256": art.sha256, "meta": art.meta, "created_at": art.created_at.isoformat(),
        "session_id": art.session_id, "project_id": art.project_id,
    }
