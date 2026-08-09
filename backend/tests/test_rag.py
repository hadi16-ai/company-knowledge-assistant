"""Unit tests for retrieve_context's query-rewrite -> retrieval wiring
(Qdrant/BM25/Gemini are mocked out at the module boundary)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from app.rag.rag import AnswerGenerationError, ConversationTurn, retrieve_context
from app.rag.retrieval import RetrievedDocument


def _match(content: str = "Annual leave is 20 days.", source: str = "handbook.pdf", page: int = 0):
    return RetrievedDocument(
        document=Document(page_content=content, metadata={"source": source, "page": page}), score=0.9
    )


def test_retrieve_context_searches_with_the_rewritten_query_not_the_raw_question():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]

    with (
        patch("app.rag.rag.rewrite_query", return_value="What was the leave policy last year?") as mock_rewrite,
        patch("app.rag.rag.retrieve_documents", return_value=[_match()]) as mock_retrieve,
    ):
        retrieve_context("What about last year?", uuid.uuid4(), history)

    mock_rewrite.assert_called_once()
    assert mock_rewrite.call_args[0][0] == "What about last year?"
    mock_retrieve.assert_called_once()
    assert mock_retrieve.call_args[0][0] == "What was the leave policy last year?"


def test_retrieve_context_passes_clamped_recent_history_to_rewrite():
    long_history = [ConversationTurn(role="user", content=f"turn {i}") for i in range(50)]

    with (
        patch("app.rag.rag.rewrite_query", return_value="question") as mock_rewrite,
        patch("app.rag.rag.retrieve_documents", return_value=[_match()]),
    ):
        retrieve_context("question", uuid.uuid4(), long_history)

    passed_history = mock_rewrite.call_args[0][1]
    assert len(passed_history) < len(long_history)


def test_retrieve_context_raises_when_nothing_is_retrieved():
    with (
        patch("app.rag.rag.rewrite_query", return_value="question"),
        patch("app.rag.rag.retrieve_documents", return_value=[]),
    ):
        with pytest.raises(AnswerGenerationError):
            retrieve_context("question", uuid.uuid4(), [])
