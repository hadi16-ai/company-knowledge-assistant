"""Document ingestion pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.embeddings import (
    EmbeddingConfigError,
    EmbeddingError,
    get_embeddings,
    validate_embeddings_connection,
)
from backend.loaders import PDFLoadError, load_pdf
from backend.splitter import split_documents
from backend.utils import is_duplicate_upload, save_uploaded_file
from backend.vectorstore import (
    VectorStoreError,
    add_documents_to_store,
    get_vectorstore,
    is_document_indexed,
)


@dataclass
class IngestResult:
    """Outcome of processing a single uploaded document."""

    filename: str
    success: bool
    message: str
    chunks_count: int = 0
    skipped: bool = False


def _process_pdf_at_path(filename: str, file_path: Path) -> IngestResult:
    """
    Load, chunk, embed, and store a PDF already present on disk.

    Args:
        filename: Display name and metadata source identifier.
        file_path: Absolute path to the PDF file.

    Returns:
        IngestResult describing success or failure.
    """
    try:
        embeddings = get_embeddings()
        vectorstore = get_vectorstore(embeddings)
        documents = load_pdf(file_path)
        chunks = split_documents(documents)

        if not chunks:
            return IngestResult(
                filename=filename,
                success=False,
                message=f"No text chunks produced from '{filename}'.",
            )

        add_documents_to_store(vectorstore, chunks)

        return IngestResult(
            filename=filename,
            success=True,
            message=f"Successfully processed '{filename}'.",
            chunks_count=len(chunks),
        )

    except EmbeddingConfigError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except PDFLoadError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except EmbeddingError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except VectorStoreError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except Exception as exc:
        return IngestResult(
            filename=filename,
            success=False,
            message=f"Unexpected error processing '{filename}': {exc}",
        )


def ingest_pdf_bytes(filename: str, file_bytes: bytes) -> IngestResult:
    """
    Run the full ingestion pipeline for one uploaded PDF.

    Steps:
        1. Duplicate check (uploads folder + vector store)
        2. Save file to disk
        3. Load PDF pages
        4. Split into chunks
        5. Generate embeddings and store in ChromaDB

    Args:
        filename: Original uploaded filename.
        file_bytes: Raw PDF bytes from the upload widget.

    Returns:
        IngestResult describing success, skip, or failure.
    """
    if not filename.lower().endswith(".pdf"):
        return IngestResult(
            filename=filename,
            success=False,
            message="Only PDF files are supported.",
        )

    if is_duplicate_upload(filename):
        return IngestResult(
            filename=filename,
            success=False,
            message=f"'{filename}' already exists in uploads. Skipping duplicate.",
            skipped=True,
        )

    try:
        embeddings = get_embeddings()
        vectorstore = get_vectorstore(embeddings)

        if is_document_indexed(vectorstore, filename):
            return IngestResult(
                filename=filename,
                success=False,
                message=f"'{filename}' is already indexed in the vector database. Skipping duplicate.",
                skipped=True,
            )

        saved_path = save_uploaded_file(filename, file_bytes)
        return _process_pdf_at_path(filename, saved_path)

    except EmbeddingConfigError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except EmbeddingError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except VectorStoreError as exc:
        return IngestResult(filename=filename, success=False, message=str(exc))
    except Exception as exc:
        return IngestResult(
            filename=filename,
            success=False,
            message=f"Unexpected error processing '{filename}': {exc}",
        )


def ingest_uploaded_files(
    uploaded_files: list[tuple[str, bytes]],
    progress_callback=None,
) -> list[IngestResult]:
    """
    Process multiple uploaded PDF files sequentially.

    Args:
        uploaded_files: List of (filename, file_bytes) tuples.
        progress_callback: Optional callable(current_index, total, filename).

    Returns:
        List of IngestResult objects, one per file.
    """
    results: list[IngestResult] = []
    total = len(uploaded_files)

    for index, (filename, file_bytes) in enumerate(uploaded_files, start=1):
        if progress_callback:
            progress_callback(index, total, filename)
        results.append(ingest_pdf_bytes(filename, file_bytes))

    return results


def check_configuration() -> str | None:
    """
    Validate local configuration without calling external APIs.

    Returns:
        None if configuration looks valid, otherwise an error message.
    """
    try:
        get_vectorstore(get_embeddings())
        return None
    except EmbeddingConfigError as exc:
        return str(exc)
    except Exception as exc:
        return f"Vector store initialization failed: {exc}"


def validate_pipeline_ready() -> str | None:
    """
    Validate that the ingestion pipeline can run, including a live embedding check.

    Returns:
        None if ready, otherwise an error message string.
    """
    config_error = check_configuration()
    if config_error:
        return config_error

    try:
        validate_embeddings_connection()
        return None
    except EmbeddingError as exc:
        return str(exc)
    except Exception as exc:
        return f"Pipeline validation failed: {exc}"


def reindex_existing_upload(filename: str) -> IngestResult:
    """
    Re-process a PDF already saved in the uploads directory.

    Useful for future admin/maintenance flows.

    Args:
        filename: Name of an existing file in data/uploads.

    Returns:
        IngestResult for the re-indexing attempt.
    """
    from backend.utils import UPLOADS_DIR

    file_path = UPLOADS_DIR / filename
    if not file_path.exists():
        return IngestResult(
            filename=filename,
            success=False,
            message=f"File '{filename}' not found in uploads.",
        )

    return _process_pdf_at_path(filename, file_path)
