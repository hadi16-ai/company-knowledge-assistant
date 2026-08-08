"""Document upload, lifecycle, and ingestion-status endpoints.

Upload is intentionally synchronous only up to "stored + queued" (architecture
review §4, Phase 1 — Upload & Queue): validate, push to MinIO, enqueue a
Celery job, and return 202 immediately. The expensive chunk/embed/store work
happens in `app.workers.tasks.process_document_task`.

Per the RBAC scoping in ARCHITECTURE_REVIEW.md §6 (applied here with the two
roles Phase 1 already has — full 5-tier RBAC is Phase 3): uploading,
replacing, re-indexing, and deleting documents are Admin-only actions.
Listing, viewing, and downloading are available to any authenticated member
of the organization.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentStatus
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user, require_admin
from app.rag.vectorstore import VectorStoreError, delete_document_chunks, get_qdrant_client
from app.schemas.document import DocumentResponse, DocumentUploadAccepted, DocumentViewUrl
from app.storage.s3 import (
    PRESIGNED_URL_EXPIRY_SECONDS,
    StorageError,
    build_object_key,
    delete_bytes,
    ensure_bucket_exists,
    generate_presigned_url,
    upload_bytes,
)
from app.workers.tasks import process_document_task

router = APIRouter(prefix="/documents", tags=["documents"])


def _validate_pdf_upload(file: UploadFile, file_bytes: bytes) -> None:
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a valid PDF.")
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit.",
        )


def _get_org_document(db: Session, document_id: uuid.UUID, org_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


def _delete_indexed_chunks(org_id: uuid.UUID, document_id: uuid.UUID) -> None:
    try:
        delete_document_chunks(get_qdrant_client(), org_id, document_id)
    except VectorStoreError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("", response_model=DocumentUploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    """Validate, store, and queue a PDF for asynchronous ingestion. Admin only."""
    file_bytes = await file.read()
    _validate_pdf_upload(file, file_bytes)

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
    return _get_org_document(db, document_id, current_user.org_id)


@router.get("/{document_id}/view-url", response_model=DocumentViewUrl)
def get_document_view_url(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentViewUrl:
    """Return a short-lived, browser-reachable URL to view or download the original PDF."""
    document = _get_org_document(db, document_id, current_user.org_id)

    try:
        url = generate_presigned_url(document.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return DocumentViewUrl(
        url=url,
        filename=document.filename,
        page_count=document.page_count,
        expires_in_seconds=PRESIGNED_URL_EXPIRY_SECONDS,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Delete a document and everything derived from it: indexed vectors, stored file, and registry row. Admin only."""
    document = _get_org_document(db, document_id, current_user.org_id)

    _delete_indexed_chunks(current_user.org_id, document.id)

    try:
        delete_bytes(document.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.delete(document)
    db.commit()


@router.put("/{document_id}", response_model=DocumentUploadAccepted)
async def replace_document(
    document_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    """Replace a document's file in place and re-run ingestion. Admin only.

    Overwrites storage and re-embeds under the same document id — this is a
    direct in-place replace, not version history (superseded-document
    tracking is a later, larger feature; see ARCHITECTURE_REVIEW.md's
    Document Versioning item).
    """
    document = _get_org_document(db, document_id, current_user.org_id)

    file_bytes = await file.read()
    _validate_pdf_upload(file, file_bytes)

    _delete_indexed_chunks(current_user.org_id, document.id)

    new_object_key = build_object_key(current_user.org_id, document.id, file.filename)
    try:
        ensure_bucket_exists()
        upload_bytes(new_object_key, file_bytes)
        if new_object_key != document.storage_path:
            delete_bytes(document.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    document.filename = file.filename
    document.storage_path = new_object_key
    document.size_bytes = len(file_bytes)
    document.status = DocumentStatus.PENDING
    document.chunk_count = 0
    document.page_count = 0
    document.error_message = None
    db.commit()

    process_document_task.delay(str(document.id))

    return DocumentUploadAccepted(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        message="Document replaced and queued for re-processing.",
    )


@router.post("/{document_id}/reindex", response_model=DocumentUploadAccepted)
def reindex_document(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    """Delete existing vectors and re-run ingestion for the current file. Admin only."""
    document = _get_org_document(db, document_id, current_user.org_id)

    _delete_indexed_chunks(current_user.org_id, document.id)

    document.status = DocumentStatus.PENDING
    document.chunk_count = 0
    document.page_count = 0
    document.error_message = None
    db.commit()

    process_document_task.delay(str(document.id))

    return DocumentUploadAccepted(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        message="Document queued for re-indexing.",
    )
