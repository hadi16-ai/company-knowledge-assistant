"""Pydantic schemas for the invitation-based org-join flow."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models import UserRole

DEFAULT_INVITATION_TTL_HOURS = 168  # 7 days


class CreateInvitationRequest(BaseModel):
    role: UserRole
    email_hint: EmailStr | None = None
    expires_in_hours: int = Field(default=DEFAULT_INVITATION_TTL_HOURS, ge=1, le=24 * 30)


class InvitationCreatedResponse(BaseModel):
    """Returned once, at creation — the only time the raw token is ever exposed."""

    id: uuid.UUID
    role: UserRole
    email_hint: str | None
    expires_at: datetime
    token: str


class InvitationResponse(BaseModel):
    """The pending-invitations list view — never includes the token or its hash."""

    id: uuid.UUID
    role: UserRole
    email_hint: str | None
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None

    model_config = {"from_attributes": True}
