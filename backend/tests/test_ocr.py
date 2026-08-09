"""Unit tests for OCR text-quality checks and cleanup (no Tesseract binary needed here —
the engine dispatch itself is exercised through mocks; see test_loaders.py for the
full load_pdf integration)."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app.rag.ocr import OCRError, clean_ocr_text, ocr_page_image, page_needs_ocr


def test_page_needs_ocr_true_for_blank_text():
    assert page_needs_ocr("") is True
    assert page_needs_ocr("   \n\n  ") is True


def test_page_needs_ocr_true_for_a_few_stray_characters():
    assert page_needs_ocr("1") is True


def test_page_needs_ocr_false_for_real_content():
    assert page_needs_ocr("Annual leave is twenty days per calendar year for every employee.") is False


def test_clean_ocr_text_collapses_repeated_blank_lines():
    raw = "Heading\n\n\n\n\nBody text."
    assert clean_ocr_text(raw) == "Heading\n\nBody text."


def test_clean_ocr_text_dehyphenates_line_wrapped_words():
    raw = "This is a hyphen-\nated word."
    assert clean_ocr_text(raw) == "This is a hyphenated word."


def test_clean_ocr_text_collapses_repeated_spaces_and_tabs():
    raw = "Too    many   spaces\tand\ttabs."
    assert clean_ocr_text(raw) == "Too many spaces and tabs."


def test_clean_ocr_text_strips_leading_and_trailing_whitespace():
    assert clean_ocr_text("  \n  Hello.  \n  ") == "Hello."


def test_ocr_page_image_uses_configured_provider():
    mock_engine = Mock(return_value="Recognized text.")
    with patch.dict("app.rag.ocr._OCR_ENGINES", {"tesseract": mock_engine}):
        result = ocr_page_image(object())

    mock_engine.assert_called_once()
    assert result == "Recognized text."


def test_ocr_page_image_wraps_engine_exception_as_ocr_error():
    mock_engine = Mock(side_effect=RuntimeError("tesseract not found"))
    with patch.dict("app.rag.ocr._OCR_ENGINES", {"tesseract": mock_engine}):
        with pytest.raises(OCRError):
            ocr_page_image(object())


def test_ocr_page_image_unknown_provider_raises():
    with patch("app.rag.ocr.get_settings") as mock_settings:
        mock_settings.return_value.ocr_provider = "not-a-real-provider"
        with pytest.raises(OCRError):
            ocr_page_image(object())
