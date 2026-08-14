"""Password hashing and JWT token management.

Passwords are hashed with Argon2id. Tokens are short-lived JWTs; refresh
tokens are additionally tracked (by SHA-256 fingerprint) in Redis so they
can be revoked. Raw tokens and passwords are never stored or logged.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

from src.core.config import Settings

_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def token_fingerprint(token: str) -> str:
    """SHA-256 fingerprint used to identify a token without storing it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(payload: dict[str, Any], secret: str) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return _encode(payload, settings.jwt_secret)


def create_refresh_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, str]:
    """Returns (token, jti). The jti is used as the Redis revocation key."""
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.refresh_token_expire_days)).timestamp()),
    }
    return _encode(payload, settings.jwt_refresh_secret), jti


def decode_token(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    """Decodes and validates a JWT. Raises jwt.InvalidTokenError on failure."""
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return payload


def refresh_cookie_max_age(settings: Settings) -> int:
    return settings.refresh_token_expire_days * 24 * 60 * 60


def refresh_cookie_attributes(settings: Settings) -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/api/v1/auth",
        "max_age": refresh_cookie_max_age(settings),
    }