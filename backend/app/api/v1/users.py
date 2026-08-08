"""Org member management: list members, change role / active status / guest expiry.

All routes are Company Admin+ (`require_company_admin`) and scoped to the
caller's own org — never accept an org id from the request, matching the
IDOR-safety pattern used everywhere else in this API (see `app/deps.py`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import can_assign_role
from app.db.models import User
from app.db.session import get_db
from app.deps import CurrentUser, require_company_admin
from app.schemas.users import OrgMemberResponse, UpdateMemberRequest

router = APIRouter(prefix="/users", tags=["users"])


def _get_org_member(db: Session, user_id: uuid.UUID, org_id: uuid.UUID) -> User:
    member = db.get(User, user_id)
    if member is None or member.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return member


@router.get("", response_model=list[OrgMemberResponse])
def list_members(
    current_user: CurrentUser = Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    """List every member of the caller's organization."""
    return list(
        db.execute(
            select(User).where(User.org_id == current_user.org_id).order_by(User.created_at)
        ).scalars()
    )


@router.patch("/{user_id}", response_model=OrgMemberResponse)
def update_member(
    user_id: uuid.UUID,
    payload: UpdateMemberRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> User:
    """Partially update a member's role, active status, or guest expiry.

    Blocked outright for the caller's own account (avoids self-lockout via
    accidental demotion/deactivation) and for targets that outrank the
    caller — a Company Admin cannot touch a Super Admin's account, only
    Super Admin can.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot edit your own account here.")

    member = _get_org_member(db, user_id, current_user.org_id)
    if not can_assign_role(current_user.role, member.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot modify a user who outranks you.")

    fields_set = payload.model_fields_set
    if "role" in fields_set and payload.role is not None:
        if not can_assign_role(current_user.role, payload.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot assign a role above your own.",
            )
        member.role = payload.role
    if "is_active" in fields_set and payload.is_active is not None:
        member.is_active = payload.is_active
    if "expires_at" in fields_set:
        member.expires_at = payload.expires_at

    db.commit()
    db.refresh(member)
    return member
