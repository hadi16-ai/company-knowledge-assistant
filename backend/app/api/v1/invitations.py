"""Invitation generation for joining an existing organization at a given role.

The raw token is only ever returned once, at creation — only its SHA-256
hash is persisted (`Invitation.token_hash`), the same pattern as an API key
or password-reset token. It's consumed by `POST /auth/register` with
`invite_token` set (see `app/api/v1/auth.py::_join_via_invitation`).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import can_assign_role
from app.db.models import Invitation
from app.db.session import get_db
from app.deps import CurrentUser, require_company_admin
from app.schemas.invitations import CreateInvitationRequest, InvitationCreatedResponse, InvitationResponse

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("", response_model=InvitationCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: CreateInvitationRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> InvitationCreatedResponse:
    """Generate a single-use invite for the caller's org at the requested role."""
    if not can_assign_role(current_user.role, payload.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot invite a role above your own.")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)

    invitation = Invitation(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
        role=payload.role,
        token_hash=token_hash,
        email_hint=payload.email_hint,
        created_by=current_user.id,
        expires_at=expires_at,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return InvitationCreatedResponse(
        id=invitation.id,
        role=invitation.role,
        email_hint=invitation.email_hint,
        expires_at=invitation.expires_at,
        token=raw_token,
    )


@router.get("", response_model=list[InvitationResponse])
def list_invitations(
    current_user: CurrentUser = Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> list[Invitation]:
    """List pending (unused, unexpired) invitations for the caller's org."""
    now = datetime.now(timezone.utc)
    return list(
        db.execute(
            select(Invitation)
            .where(
                Invitation.org_id == current_user.org_id,
                Invitation.used_at.is_(None),
                Invitation.expires_at > now,
            )
            .order_by(Invitation.created_at.desc())
        ).scalars()
    )


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> None:
    """Revoke a pending invitation so its token can no longer be consumed."""
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    db.delete(invitation)
    db.commit()
