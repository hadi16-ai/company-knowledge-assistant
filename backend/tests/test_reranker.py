"""Unit tests for cross-encoder reranking (CrossEncoder itself is mocked out — no model download in tests)."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.documents import Document

from app.rag.reranker import rerank


def test_rerank_empty_candidates_returns_empty():
    assert rerank("query", [], top_k=5) == []


def test_rerank_orders_by_cross_encoder_score_and_caps_at_top_k():
    docs = [Document(page_content=f"doc {i}") for i in range(3)]
    candidates = [(docs[0], 0.1), (docs[1], 0.9), (docs[2], 0.5)]

    # Raw logits: doc[1] should win despite having the lowest upstream RRF score.
    with patch("app.rag.reranker._get_cross_encoder") as mock_get_encoder:
        mock_get_encoder.return_value.predict.return_value = [-2.0, 5.0, 0.0]

        results = rerank("query", candidates, top_k=2)

    assert len(results) == 2
    assert results[0][0] is docs[1]
    assert results[1][0] is docs[2]


def test_rerank_scores_are_squashed_into_zero_one_range():
    docs = [Document(page_content="doc")]
    candidates = [(docs[0], 0.5)]

    with patch("app.rag.reranker._get_cross_encoder") as mock_get_encoder:
        mock_get_encoder.return_value.predict.return_value = [10.0]  # unbounded raw logit

        results = rerank("query", candidates, top_k=1)

    assert 0.0 <= results[0][1] <= 1.0


def test_rerank_falls_back_to_upstream_order_when_model_unavailable():
    from app.rag.reranker import RerankError

    docs = [Document(page_content=f"doc {i}") for i in range(2)]
    candidates = [(docs[0], 0.9), (docs[1], 0.1)]

    with patch("app.rag.reranker._get_cross_encoder", side_effect=RerankError("model unavailable")):
        results = rerank("query", candidates, top_k=5)

    assert results == candidates
