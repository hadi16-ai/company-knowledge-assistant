"""Pydantic schemas for chat / Q&A endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurnRequest(BaseModel):
    """One prior turn of the conversation, sent by the client so the assistant has memory."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Capped well above the server-side memory window (settings.conversation_memory_turns)
    # so a long-running chat session can't be used to smuggle unbounded prompt content.
    history: list[ConversationTurnRequest] = Field(default_factory=list, max_length=20)


class SourceCitationResponse(BaseModel):
    filename: str
    page_number: int | None
    excerpt: str
    score: float
    document_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceCitationResponse]


class QueryLogEntry(BaseModel):
    """One persisted question/answer turn, used to restore a user's chat history."""

    id: uuid.UUID
    query: str
    answer: str
    created_at: datetime

    model_config = {"from_attributes": True}
