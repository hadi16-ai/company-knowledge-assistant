"""Password hashing and JWT access/refresh token utilities."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """Raised when a JWT cannot be decoded or has an unexpected type."""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash."""
    return _pwd_context.verify(plain_password, password_hash)


def _create_token(
    subject: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "org_id": str(org_id),
        "role": role,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: uuid.UUID, org_id: uuid.UUID, role: str, expires_delta: timedelta | None = None
) -> str:
    """Create a short-lived access token carrying user_id, org_id, and role.

    `expires_delta` overrides the configured default TTL — used to clamp a
    guest's token to their `expires_at` (see `app.core.rbac.guest_access_ttl`).
    """
    settings = get_settings()
    return _create_token(
        subject,
        org_id,
        role,
        TokenType.ACCESS,
        expires_delta if expires_delta is not None else timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    """Create a long-lived refresh token."""
    settings = get_settings()
    return _create_token(
        subject,
        org_id,
        role,
        TokenType.REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> dict:
    """Decode and validate a JWT, enforcing the expected token type.

    Raises:
        InvalidTokenError: If the token is malformed, expired, or the wrong type.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token.")

    return payload
