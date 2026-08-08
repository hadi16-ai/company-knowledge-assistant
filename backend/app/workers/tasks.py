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
                pages = load_pdf(tmp_path)
                chunks = split_documents(pages)
            except PDFLoadError as exc:
                _mark_failed(db, document, str(exc))
                return

            if not chunks:
                _mark_failed(db, document, f"No text chunks produced from '{document.filename}'.")
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
        document.page_count = len(pages)
        document.error_message = None
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
