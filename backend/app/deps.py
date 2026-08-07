"""Shared FastAPI dependencies: DB session and JWT-authenticated current user.

Per architecture review §6: every handler reads ``org_id`` and ``role`` from
the decoded JWT, never from request parameters, so a user cannot access
another organization's data by editing an id in the request (IDOR).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.models import User, UserRole
from app.db.session import get_db

_bearer_scheme = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class CurrentUser:
    """Identity extracted from a validated access token."""

    id: uuid.UUID
    org_id: uuid.UUID
    role: UserRole


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    """Decode and validate the bearer access token, returning the caller's identity."""
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        org_id=uuid.UUID(payload["org_id"]),
        role=UserRole(payload["role"]),
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that additionally enforces the caller has the admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires administrator privileges.",
        )
    return current_user


def get_current_db_user(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Load the full User ORM row for the authenticated caller."""
    user = db.get(User, current_user.id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive.",
        )
    return user
