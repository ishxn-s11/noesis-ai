"""Audit logging for security-relevant actions."""
from sqlalchemy.orm import Session

from app.database.models import AuditLog


def audit(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    action: str,
    resource: str = "",
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            details=details or {},
        )
    )
    db.commit()
