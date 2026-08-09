"""Unit tests for PDF loading + OCR routing.

Tesseract itself is mocked out (`app.rag.loaders.ocr_pdf_page`) so these run
without a real OCR engine — the fixtures below are minimal real PDFs built
with PyMuPDF so PyPDFLoader has genuine bytes to parse; only the OCR
recognition step is faked, matching how the reranker/cross-encoder tests
mock out their model instead of loading real weights.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import pytest

from app.rag.loaders import PDFLoadError, load_pdf
from app.rag.ocr import OCRError


def _write_pdf(path: Path, page_texts: list[str | None]) -> None:
    """Write a minimal PDF. `None` produces a blank page (simulates a scanned/no-text-layer page)."""
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_load_pdf_extracts_text_layer_without_ocr(tmp_path):
    pdf_path = tmp_path / "handbook.pdf"
    _write_pdf(pdf_path, page_texts=["Annual leave is twenty days per calendar year for every employee."])

    with patch("app.rag.loaders.ocr_pdf_page") as mock_ocr:
        result = load_pdf(pdf_path)

    mock_ocr.assert_not_called()
    assert len(result.pages) == 1
    assert "Annual leave" in result.pages[0].page_content
    assert result.pages[0].metadata["source"] == "handbook.pdf"
    assert result.pages[0].metadata["page"] == 0
    assert "ocr" not in result.pages[0].metadata
    assert result.ocr_warnings == []


def test_load_pdf_routes_blank_page_through_ocr(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf(pdf_path, page_texts=[None])

    with patch("app.rag.loaders.ocr_pdf_page", return_value="Recognized scanned text.") as mock_ocr:
        result = load_pdf(pdf_path)

    mock_ocr.assert_called_once()
    assert result.pages[0].page_content == "Recognized scanned text."
    assert result.pages[0].metadata["ocr"] is True
    assert result.pages[0].metadata["source"] == "scanned.pdf"
    assert result.pages[0].metadata["page"] == 0
    assert result.ocr_warnings == []


def test_load_pdf_handles_mixed_text_and_scanned_pages(tmp_path):
    pdf_path = tmp_path / "mixed.pdf"
    _write_pdf(
        pdf_path,
        page_texts=["This page has a normal, perfectly readable text layer already present.", None],
    )

    with patch("app.rag.loaders.ocr_pdf_page", return_value="OCR recognized this second page.") as mock_ocr:
        result = load_pdf(pdf_path)

    assert mock_ocr.call_count == 1
    assert "normal" in result.pages[0].page_content
    assert "ocr" not in result.pages[0].metadata
    assert result.pages[1].page_content == "OCR recognized this second page."
    assert result.pages[1].metadata["ocr"] is True


def test_load_pdf_surfaces_ocr_failure_as_warning_not_crash(tmp_path):
    pdf_path = tmp_path / "unreadable-scan.pdf"
    _write_pdf(pdf_path, page_texts=[None])

    with patch("app.rag.loaders.ocr_pdf_page", side_effect=OCRError("tesseract not found")):
        result = load_pdf(pdf_path)

    assert result.pages[0].page_content == ""
    assert "ocr" not in result.pages[0].metadata
    assert len(result.ocr_warnings) == 1
    assert "Page 1" in result.ocr_warnings[0]


def test_load_pdf_warns_when_ocr_finds_nothing_readable(tmp_path):
    pdf_path = tmp_path / "blank-scan.pdf"
    _write_pdf(pdf_path, page_texts=[None])

    with patch("app.rag.loaders.ocr_pdf_page", return_value=""):
        result = load_pdf(pdf_path)

    assert result.pages[0].page_content == ""
    assert len(result.ocr_warnings) == 1
    assert "no readable text" in result.ocr_warnings[0]


def test_load_pdf_missing_file_raises():
    with pytest.raises(PDFLoadError):
        load_pdf(Path("/nonexistent/file.pdf"))


def test_load_pdf_empty_file_raises(tmp_path):
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"")
    with pytest.raises(PDFLoadError):
        load_pdf(pdf_path)


def test_load_pdf_respects_ocr_disabled_setting(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf(pdf_path, page_texts=[None])

    with patch("app.rag.loaders.get_settings") as mock_settings:
        mock_settings.return_value.ocr_enabled = False
        with patch("app.rag.loaders.ocr_pdf_page") as mock_ocr:
            result = load_pdf(pdf_path)

    mock_ocr.assert_not_called()
    assert result.ocr_warnings == []
    assert result.pages[0].page_content == ""
