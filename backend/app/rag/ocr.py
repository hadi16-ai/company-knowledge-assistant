"""OCR fallback for scanned or low-text PDF pages.

Runs entirely locally via Tesseract (no external API call during ingestion,
matching this app's fully-local ingestion principle — see CLAUDE.md). The
engine lookup in ``_OCR_ENGINES`` is the single swap point for a future cloud
OCR provider (Textract, Google Vision, ...): add an entry there and point
``OCR_PROVIDER`` at it, no caller changes needed.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable

import pymupdf as fitz  # `fitz` is PyMuPDF's now-deprecated import alias; `pymupdf` is the current name
import pytesseract
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# A page counts as needing OCR when its extracted text layer is this thin or
# thinner. Scanned pages typically carry zero (or stray OCR-artifact) embedded
# text, while a genuine text page carries hundreds of characters even when short.
MIN_TEXT_LAYER_CHARS = 20

# Render resolution before handing a page to Tesseract. High enough to resolve
# normal body text reliably, without the multi-second/high-memory cost of
# print-quality (600 DPI+) rendering.
OCR_RENDER_DPI = 300


class OCRError(Exception):
    """Raised when OCR rendering or recognition fails for a page."""


def page_needs_ocr(text: str) -> bool:
    """Return True when a page's extracted text layer is too thin to be real content."""
    return len(text.strip()) < MIN_TEXT_LAYER_CHARS


def clean_ocr_text(raw: str) -> str:
    """Normalize common Tesseract artifacts into text suitable for chunking/embedding."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # rejoin words hyphen-wrapped across a line break
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tesseract_ocr(image: Image.Image) -> str:
    return pytesseract.image_to_string(image)


_OCR_ENGINES: dict[str, Callable[[Image.Image], str]] = {
    "tesseract": _tesseract_ocr,
}


def render_page_to_image(pdf_document: fitz.Document, page_index: int) -> Image.Image:
    """Rasterize one PDF page (0-indexed) to a PIL image at OCR resolution."""
    try:
        page = pdf_document.load_page(page_index)
        zoom = OCR_RENDER_DPI / 72
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.open(io.BytesIO(pixmap.tobytes("png")))
    except Exception as exc:
        raise OCRError(f"Failed to render page {page_index + 1} for OCR: {exc}") from exc


def ocr_page_image(image: Image.Image) -> str:
    """Run the configured OCR engine on a page image and return cleaned text."""
    provider = get_settings().ocr_provider
    engine = _OCR_ENGINES.get(provider)
    if engine is None:
        raise OCRError(f"Unknown OCR provider '{provider}'.")
    try:
        raw_text = engine(image)
    except Exception as exc:
        raise OCRError(f"OCR recognition failed: {exc}") from exc
    return clean_ocr_text(raw_text)


def ocr_pdf_page(pdf_document: fitz.Document, page_index: int) -> str:
    """Render and OCR one page (0-indexed) of an already-open PDF.

    Raises:
        OCRError: If rendering or recognition fails for this page.
    """
    image = render_page_to_image(pdf_document, page_index)
    return ocr_page_image(image)
