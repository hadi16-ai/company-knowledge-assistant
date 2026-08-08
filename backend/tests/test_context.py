"""Unit tests for RAG context construction and citation building."""

from __future__ import annotations

from langchain_core.documents import Document

from app.rag.context import build_context
from app.rag.retrieval import RetrievedDocument


def _match(
    content: str,
    source: str = "handbook.pdf",
    page: int = 0,
    score: float = 0.8,
    doc_id: str | None = None,
) -> RetrievedDocument:
    metadata = {"source": source, "page": page}
    if doc_id is not None:
        metadata["doc_id"] = doc_id
    return RetrievedDocument(
        document=Document(page_content=content, metadata=metadata),
        score=score,
    )


def test_build_context_labels_sources_and_pages():
    matches = [_match("Annual leave is 20 days.", page=4)]

    context, citations = build_context(matches)

    assert "[Source 1: handbook.pdf, page 5]" in context
    assert "Annual leave is 20 days." in context
    assert len(citations) == 1
    assert citations[0].filename == "handbook.pdf"
    assert citations[0].page_number == 5
    assert citations[0].score == 0.8


def test_build_context_skips_empty_chunks():
    matches = [_match(""), _match("Real content.")]

    context, citations = build_context(matches)

    assert "Real content." in context
    assert len(citations) == 1


def test_build_context_respects_character_budget():
    matches = [_match("a" * 100), _match("b" * 100)]

    context, citations = build_context(matches, max_context_characters=120)

    assert len(citations) == 2
    assert len(citations[1].excerpt) == 20  # only 20 chars of budget remained
    assert sum(len(c.excerpt) for c in citations) == 120


def test_build_context_empty_matches_returns_empty():
    context, citations = build_context([])
    assert context == ""
    assert citations == []


def test_build_context_carries_document_id_for_clickable_citations():
    matches = [_match("Annual leave is 20 days.", doc_id="11111111-1111-1111-1111-111111111111")]

    _, citations = build_context(matches)

    assert citations[0].document_id == "11111111-1111-1111-1111-111111111111"


def test_build_context_document_id_defaults_to_none_when_absent():
    matches = [_match("Annual leave is 20 days.")]

    _, citations = build_context(matches)

    assert citations[0].document_id is None
