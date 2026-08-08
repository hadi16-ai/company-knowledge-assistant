"""Unit tests for password hashing and JWT token utilities."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(user_id, org_id, "admin")

    payload = decode_token(token, TokenType.ACCESS)

    assert payload["sub"] == str(user_id)
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_rejected_as_access_token():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    refresh_token = create_refresh_token(user_id, org_id, "employee")

    with pytest.raises(InvalidTokenError):
        decode_token(refresh_token, TokenType.ACCESS)


def test_garbage_token_rejected():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-token", TokenType.ACCESS)


def test_access_token_respects_expires_delta_override():
    """Used to clamp a guest's token TTL to their expires_at (app.core.rbac)."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    # JWT `exp` is encoded as an integer Unix timestamp, so bound the window
    # with a 1s tolerance rather than comparing to microsecond precision.
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = create_access_token(user_id, org_id, "guest", expires_delta=timedelta(minutes=5))
    after = datetime.now(timezone.utc) + timedelta(seconds=1)

    payload = decode_token(token, TokenType.ACCESS)
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert before + timedelta(minutes=5) <= exp <= after + timedelta(minutes=5)
