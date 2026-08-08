"""Cross-encoder reranking of retrieved chunks.

A bi-encoder (the embedding model) scores query and document independently
then compares vectors — fast, but blind to query/document interaction. A
cross-encoder scores the (query, document) pair jointly, which is far more
accurate but too slow to run over a whole collection. Run it only on the
narrow candidate set hybrid retrieval already narrowed down to. See
ARCHITECTURE_REVIEW.md §4/§8.
"""

from __future__ import annotations

import math
from functools import lru_cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from app.core.config import get_settings


class RerankError(Exception):
    """Raised when cross-encoder reranking cannot be completed."""


@lru_cache
def _get_cross_encoder() -> CrossEncoder:
    model_name = get_settings().reranker_model
    try:
        return CrossEncoder(model_name)
    except Exception as exc:
        raise RerankError(f"Failed to load reranker model '{model_name}': {exc}") from exc


def rerank(query: str, candidates: list[tuple[Document, float]], top_k: int) -> list[tuple[Document, float]]:
    """
    Rerank a candidate set by cross-encoder relevance, returning the top-k.

    Args:
        query: The user's question.
        candidates: (document, upstream_score) pairs from hybrid retrieval,
            already merged via RRF. `upstream_score` is only used as a
            fallback if reranking is unavailable.
        top_k: Number of results to return after reranking.

    Returns:
        (document, cross_encoder_score) pairs, best first, capped at top_k.
        Falls back to the incoming order (upstream RRF score) if the
        reranker model cannot be loaded, so a model download hiccup
        degrades retrieval quality rather than breaking it outright.
    """
    if not candidates:
        return []

    try:
        encoder = _get_cross_encoder()
        pairs = [(query, document.page_content) for document, _ in candidates]
        raw_scores = encoder.predict(pairs)
    except RerankError:
        return candidates[:top_k]

    # ms-marco-MiniLM-L-6-v2 outputs unbounded logits, not a [0, 1] score —
    # squash with a sigmoid so the UI's confidence display stays meaningful.
    scored = [(document, 1.0 / (1.0 + math.exp(-float(score)))) for (document, _), score in zip(candidates, raw_scores)]
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
