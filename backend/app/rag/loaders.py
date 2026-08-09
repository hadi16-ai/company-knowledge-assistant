"""Document loading utilities.

Text-layer extraction runs first via PyPDFLoader (unchanged from the original
pipeline). Any page whose extracted text is too thin to be real content —
i.e. a scanned/image-only page — is then routed through ``app.rag.ocr`` so
the whole document, not just its text pages, ends up usable by chunking and
embedding. Page/source metadata is left untouched either way, so citations
and the PDF viewer (which key off ``metadata["page"]``) keep working exactly
as before for every page, OCR'd or not.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz  # `fitz` is PyMuPDF's now-deprecated import alias; `pymupdf` is the current name
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from app.core.config import get_settings
from app.rag.ocr import OCRError, ocr_pdf_page, page_needs_ocr

logger = logging.getLogger(__name__)


class PDFLoadError(Exception):
    """Raised when a PDF file cannot be loaded or parsed."""


@dataclass(frozen=True)
class PDFLoadResult:
    """Loaded pages plus any non-fatal issues hit while OCR'ing scanned pages."""

    pages: list[Document]
    ocr_warnings: list[str]


def load_pdf(file_path: Path) -> PDFLoadResult:
    """
    Load a PDF file and return one Document per page, running OCR on any
    page whose embedded text layer is too thin to be real content.

    Args:
        file_path: Path to the PDF file on disk (a local temp copy during ingestion).

    Returns:
        Loaded pages plus human-readable warnings for pages where OCR was
        attempted but could not recover any text (the page is kept, just
        with empty content, rather than being dropped from the document).

    Raises:
        PDFLoadError: If the file is missing, empty, or cannot be parsed at all.
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
        doc.metadata["source"] = file_path.name

    ocr_warnings = _apply_ocr_to_scanned_pages(file_path, documents)

    return PDFLoadResult(pages=documents, ocr_warnings=ocr_warnings)


def _apply_ocr_to_scanned_pages(file_path: Path, documents: list[Document]) -> list[str]:
    """Mutate `documents` in place, replacing thin-text pages with OCR'd text.

    Returns a list of human-readable warnings for pages where OCR was
    attempted but failed or found nothing — never raises, so one bad scanned
    page never takes down ingestion of an otherwise-good document.
    """
    if not get_settings().ocr_enabled:
        return []

    scanned_pages = [(index, doc) for index, doc in enumerate(documents) if page_needs_ocr(doc.page_content)]
    if not scanned_pages:
        return []

    try:
        pdf_document = fitz.open(str(file_path))
    except Exception as exc:
        logger.warning("Could not open '%s' for OCR: %s", file_path.name, exc)
        return [f"OCR could not run on {len(scanned_pages)} scanned page(s): {exc}"]

    warnings: list[str] = []
    try:
        for index, doc in scanned_pages:
            page_number = doc.metadata.get("page")
            page_number = page_number if isinstance(page_number, int) else index
            try:
                ocr_text = ocr_pdf_page(pdf_document, page_number)
            except OCRError as exc:
                logger.warning("OCR failed on '%s' page %d: %s", file_path.name, page_number + 1, exc)
                warnings.append(f"Page {page_number + 1}: OCR failed ({exc})")
                continue
            if ocr_text:
                doc.page_content = ocr_text
                doc.metadata["ocr"] = True
            else:
                warnings.append(f"Page {page_number + 1}: OCR found no readable text")
    finally:
        pdf_document.close()

    return warnings
