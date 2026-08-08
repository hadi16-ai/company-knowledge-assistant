"""Authentication endpoints: register, login, refresh, current user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User, UserRole
from app.db.seed import ensure_default_organization
from app.db.session import get_db
from app.deps import CurrentUser, get_current_db_user, get_current_user
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new user account under the default organization.

    Phase 1 is single-tenant: every user lands in the seeded default
    organization. The first registered user becomes an admin so there is
    always someone able to manage the workspace; everyone after is an
    employee.
    """
    existing = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    org = ensure_default_organization(db)
    is_first_user = db.query(User).filter(User.org_id == org.id).count() == 0

    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN if is_first_user else UserRole.EMPLOYEE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id, user.org_id, user.role.value),
        refresh_token=create_refresh_token(user.id, user.org_id, user.role.value),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate with email/password and issue an access + refresh token pair."""
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")

    return TokenResponse(
        access_token=create_access_token(user.id, user.org_id, user.role.value),
        refresh_token=create_refresh_token(user.id, user.org_id, user.role.value),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        claims = decode_token(payload.refresh_token, TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid refresh token: {exc}") from exc

    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found or inactive.")

    return TokenResponse(
        access_token=create_access_token(user.id, user.org_id, user.role.value),
        refresh_token=create_refresh_token(user.id, user.org_id, user.role.value),
    )


@router.get("/me", response_model=UserResponse)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    user: User = Depends(get_current_db_user),
) -> UserResponse:
    """Return the authenticated caller's profile."""
    return UserResponse(
        id=user.id,
        org_id=user.org_id,
        org_name=user.organization.name,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )
