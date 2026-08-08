"""Shared FastAPI dependencies: DB session and JWT-authenticated current user.

Per architecture review §6: every handler reads ``org_id`` and ``role`` from
the decoded JWT, never from request parameters, so a user cannot access
another organization's data by editing an id in the request (IDOR).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.rbac import has_at_least, is_guest_access_expired
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


def require_role(minimum: UserRole):
    """Dependency factory: enforces the caller's role outranks or equals `minimum`.

    Rank order (highest first): SUPER_ADMIN > COMPANY_ADMIN > MANAGER >
    EMPLOYEE > GUEST — see `app.core.rbac.ROLE_RANK`.
    """

    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_at_least(current_user.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {minimum.value} role or above.",
            )
        return current_user

    return _check


# Convenience aliases for the rank thresholds routers actually gate on.
require_manager = require_role(UserRole.MANAGER)
require_company_admin = require_role(UserRole.COMPANY_ADMIN)


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
    if is_guest_access_expired(user.role, user.expires_at, datetime.now(timezone.utc)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This guest account's access has expired.",
        )
    return user
