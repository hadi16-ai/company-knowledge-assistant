"""Document loading utilities."""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document


class PDFLoadError(Exception):
    """Raised when a PDF file cannot be loaded or parsed."""


def load_pdf(file_path: Path) -> list[Document]:
    """
    Load a PDF file and return LangChain Document objects.

    Args:
        file_path: Path to the PDF file on disk (a local temp copy during ingestion).

    Returns:
        List of documents, one per page.

    Raises:
        PDFLoadError: If the file is missing, empty, or cannot be parsed.
    """
    if not file_path.exists():
        raise PDFLoadError(f"File not found: {file_path.name}")

    if file_path.stat().st_size == 0:
        raise PDFLoadError(f"File is empty: {file_path.name}")

    try:
        loader = PyPDFLoader(str(file_path))
        documents = loader.load()
    except Exception as exc:
        raise PDFLoadError(f"Failed to load PDF '{file_path.name}': {exc}") from exc

    if not documents:
        raise PDFLoadError(f"No content extracted from PDF: {file_path.name}")

    for doc in documents:
        doc.metadata.setdefault("source", file_path.name)

    return documents
