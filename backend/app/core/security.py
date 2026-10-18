"""Password hashing (PBKDF2, stdlib only) and JWT issue/verify."""
import hashlib
import hmac
import os
import time
from typing import Any

import jwt

from app.core.config import settings

PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: str, tenant_id: str, role: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
        "iss": "noesis-ai",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="noesis-ai",
        )
    except jwt.PyJWTError:
        return None
