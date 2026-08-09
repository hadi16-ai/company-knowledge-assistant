"""Pydantic schemas for conversation/thread endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationMessage(BaseModel):
    """One persisted question/answer turn within a conversation."""

    id: uuid.UUID
    query: str
    answer: str
    created_at: datetime

    model_config = {"from_attributes": True}
