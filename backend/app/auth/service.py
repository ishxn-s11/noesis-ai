"""Authentication: tenant-scoped registration, login, JWT identity."""
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthErr, ConflictErr
from app.core.security import create_access_token, hash_password, verify_password
from app.database.models import Tenant, User
from app.database.session import get_db, set_tenant
from app.core.events import audit

bearer_scheme = HTTPBearer(auto_error=False)


def _slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def register_user(
    db: Session,
    *,
    tenant_name: str,
    email: str,
    password: str,
    full_name: str = "",
) -> dict:
    email = email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictErr("Email already registered")
    tenant = db.scalar(select(Tenant).where(Tenant.name == tenant_name.strip()))
    if not tenant:
        slug = _slugify(tenant_name)
        if db.scalar(select(Tenant).where(Tenant.slug == slug)):
            slug = f"{slug}-{_uuid6()}"
        tenant = Tenant(name=tenant_name.strip(), slug=slug)
        db.add(tenant)
        db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role="admin" if db.scalar(select(User).where(User.tenant_id == tenant.id)) is None else "researcher",
    )
    db.add(user)
    db.commit()
    audit(db, tenant_id=tenant.id, user_id=user.id, action="auth.register", resource=email)
    return _token_response(user)


def login_user(db: Session, *, email: str, password: str) -> dict:
    email = email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise AuthErr("Invalid credentials")
    audit(db, tenant_id=user.tenant_id, user_id=user.id, action="auth.login", resource=email)
    return _token_response(user)


def _token_response(user: User) -> dict:
    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
        },
    }


def _uuid6() -> str:
    import uuid

    return uuid.uuid4().hex[:6]


@dataclass
class CurrentUser:
    id: str
    tenant_id: str
    email: str
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise AuthErr("Missing bearer token")
    from app.core.security import decode_access_token

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise AuthErr("Invalid or expired token")
    user = db.scalar(select(User).where(User.id == payload["sub"], User.is_active == True))  # noqa: E712
    if not user:
        raise AuthErr("Unknown user")
    set_tenant(db, user.tenant_id)
    return CurrentUser(
        id=user.id, tenant_id=user.tenant_id, email=user.email, role=user.role
    )
