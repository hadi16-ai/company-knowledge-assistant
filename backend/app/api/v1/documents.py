"""Document upload and ingestion-status endpoints.

Upload is intentionally synchronous only up to "stored + queued" (architecture
review §4, Phase 1 — Upload & Queue): validate, push to MinIO, enqueue a
Celery job, and return 202 immediately. The expensive chunk/embed/store work
happens in `app.workers.tasks.process_document_task`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentStatus
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.schemas.document import DocumentResponse, DocumentUploadAccepted
from app.storage.s3 import StorageError, build_object_key, ensure_bucket_exists, upload_bytes
from app.workers.tasks import process_document_task

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    """Validate, store, and queue a PDF for asynchronous ingestion."""
    settings = get_settings()

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a valid PDF.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit.",
        )

    existing = db.execute(
        select(Document).where(
            Document.org_id == current_user.org_id,
            Document.filename == file.filename,
            Document.status != DocumentStatus.FAILED,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{file.filename}' has already been uploaded to this workspace.",
        )

    document = Document(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
        created_by=current_user.id,
        filename=file.filename,
        storage_path="",
        status=DocumentStatus.PENDING,
        size_bytes=len(file_bytes),
    )
    object_key = build_object_key(current_user.org_id, document.id, file.filename)
    document.storage_path = object_key

    try:
        ensure_bucket_exists()
        upload_bytes(object_key, file_bytes)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.add(document)
    db.commit()
    db.refresh(document)

    process_document_task.delay(str(document.id))

    return DocumentUploadAccepted(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        message="Document uploaded and queued for processing.",
    )


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    """List all documents uploaded to the caller's organization."""
    return list(
        db.execute(
            select(Document)
            .where(Document.org_id == current_user.org_id)
            .order_by(Document.created_at.desc())
        ).scalars()
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    """Fetch a single document's ingestion status, scoped to the caller's org."""
    document = db.get(Document, document_id)
    if document is None or document.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document
