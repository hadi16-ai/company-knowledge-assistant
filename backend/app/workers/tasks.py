"""Celery tasks implementing the async ingestion pipeline."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from app.db.base import SessionLocal
from app.db.models import Document, DocumentStatus
from app.rag.embeddings import EmbeddingConfigError, EmbeddingError, get_embeddings
from app.rag.loaders import PDFLoadError, load_pdf
from app.rag.splitter import split_documents
from app.rag.vectorstore import VectorStoreError, add_documents_to_store, get_vectorstore
from app.storage.s3 import StorageError, download_bytes
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.process_document_task", bind=True, max_retries=2)
def process_document_task(self, document_id: str) -> None:
    """
    Load a previously-uploaded document from object storage, chunk it,
    embed the chunks, and store them in the organization's Qdrant collection.

    Args:
        document_id: UUID (as string) of the `documents` row to process.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            logger.error("Document %s not found; skipping.", document_id)
            return

        document.status = DocumentStatus.PROCESSING
        db.commit()

        try:
            file_bytes = download_bytes(document.storage_path)
        except StorageError as exc:
            _mark_failed(db, document, str(exc))
            return

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / document.filename
            tmp_path.write_bytes(file_bytes)

            try:
                loaded = load_pdf(tmp_path)
                chunks = split_documents(loaded.pages)
            except PDFLoadError as exc:
                _mark_failed(db, document, str(exc))
                return

            if not chunks:
                reason = (
                    f"OCR could not extract readable text from any page of '{document.filename}' "
                    "(scanned document) — nothing to index."
                    if loaded.ocr_warnings
                    else f"No text chunks produced from '{document.filename}'."
                )
                _mark_failed(db, document, reason)
                return

            try:
                embeddings = get_embeddings()
                vectorstore = get_vectorstore(embeddings, document.org_id)
                add_documents_to_store(vectorstore, chunks, document.org_id, document.id)
            except (EmbeddingConfigError, EmbeddingError, VectorStoreError) as exc:
                _mark_failed(db, document, str(exc))
                return

        document.status = DocumentStatus.READY
        document.chunk_count = len(chunks)
        document.page_count = len(loaded.pages)
        # Reuses error_message as a non-fatal processing note on an otherwise
        # successful document — e.g. a handful of scanned pages OCR couldn't
        # read — rather than a schema addition just for warning text. The
        # document is still READY; the frontend renders this distinctly from
        # a FAILED document's error_message.
        document.error_message = (
            f"{len(loaded.ocr_warnings)} page(s) needed OCR and could not be fully read: "
            + "; ".join(loaded.ocr_warnings)
            if loaded.ocr_warnings
            else None
        )
        db.commit()
        logger.info("Document %s processed successfully (%d chunks).", document_id, len(chunks))

    except Exception as exc:  # noqa: BLE001 - last-resort guard so the worker never crashes silently
        logger.exception("Unexpected error processing document %s", document_id)
        document = db.get(Document, uuid.UUID(document_id))
        if document is not None:
            _mark_failed(db, document, f"Unexpected error: {exc}")
    finally:
        db.close()


def _mark_failed(db, document: Document, message: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error_message = message
    db.commit()
    logger.warning("Document %s failed: %s", document.id, message)
