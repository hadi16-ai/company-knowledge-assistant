"""Authentication endpoints: register, login, refresh, current user."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rbac import guest_access_ttl, is_guest_access_expired
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import Invitation, Organization, User, UserRole
from app.db.session import get_db
from app.deps import CurrentUser, get_current_db_user, get_current_user
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_STRIP_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "org"


def _unique_org_slug(db: Session, name: str) -> str:
    """Return a slug for `name`, disambiguated with a short suffix on collision."""
    base = _slugify(name)
    slug = base
    suffix = 1
    while db.query(Organization).filter(Organization.slug == slug).one_or_none() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_org_and_admin(db: Session, payload: RegisterRequest) -> User:
    org = Organization(id=uuid.uuid4(), name=payload.organization_name, slug=_unique_org_slug(db, payload.organization_name))
    db.add(org)
    db.flush()  # populate org.id for the FK below without a full commit yet

    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.COMPANY_ADMIN,
    )
    db.add(user)
    return user


def _join_via_invitation(db: Session, payload: RegisterRequest) -> User:
    token_hash = _hash_invite_token(payload.invite_token)
    now = datetime.now(timezone.utc)
    invitation = db.query(Invitation).filter(Invitation.token_hash == token_hash).one_or_none()
    if invitation is None or invitation.used_at is not None or invitation.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invite link is invalid or has expired.")
    if invitation.email_hint is not None and invitation.email_hint.lower() != payload.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite was issued for a different email address.",
        )

    user = User(
        id=uuid.uuid4(),
        org_id=invitation.org_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=invitation.role,
    )
    db.add(user)
    db.flush()
    invitation.used_at = now
    invitation.used_by = user.id
    return user


def _issue_tokens(user: User) -> TokenResponse:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    default_ttl = timedelta(minutes=settings.access_token_expire_minutes)
    access_ttl = guest_access_ttl(default_ttl, user.role, user.expires_at, now)
    return TokenResponse(
        access_token=create_access_token(user.id, user.org_id, user.role.value, expires_delta=access_ttl),
        refresh_token=create_refresh_token(user.id, user.org_id, user.role.value),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new user account, either founding a new organization or joining one via invite.

    `RegisterRequest` enforces exactly one of `organization_name` (create a
    new org, caller becomes its Company Admin) or `invite_token` (join an
    existing org with the role and email restriction the invite specifies).
    """
    existing = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    if payload.organization_name:
        user = _create_org_and_admin(db, payload)
    else:
        user = _join_via_invitation(db, payload)

    db.commit()
    db.refresh(user)

    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate with email/password and issue an access + refresh token pair."""
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")
    if is_guest_access_expired(user.role, user.expires_at, datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This guest account's access has expired.")

    return _issue_tokens(user)


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
    if is_guest_access_expired(user.role, user.expires_at, datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This guest account's access has expired.")

    return _issue_tokens(user)


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
        expires_at=user.expires_at,
    )
