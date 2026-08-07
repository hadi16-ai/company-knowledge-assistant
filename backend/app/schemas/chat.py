"""Pydantic schemas for chat / Q&A endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SourceCitationResponse(BaseModel):
    filename: str
    page_number: int | None
    excerpt: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceCitationResponse]
