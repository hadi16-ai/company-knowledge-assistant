"""Pydantic schemas for org member management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.models import UserRole


class OrgMemberResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateMemberRequest(BaseModel):
    """Partial update — only the fields an admin actually wants to change."""

    role: UserRole | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
