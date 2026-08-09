"""Pydantic schemas for chat / Q&A endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Identifies which thread this question belongs to — conversation memory
    # is loaded server-side from this conversation's own query_log rows
    # (see app.api.v1.chat), never trusted from client-submitted history.
    conversation_id: uuid.UUID


class SourceCitationResponse(BaseModel):
    filename: str
    page_number: int | None
    excerpt: str
    score: float
    document_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceCitationResponse]
