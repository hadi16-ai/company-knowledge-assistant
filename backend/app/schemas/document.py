"""Pydantic schemas for document ingestion endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: DocumentStatus
    chunk_count: int
    size_bytes: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadAccepted(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    message: str
