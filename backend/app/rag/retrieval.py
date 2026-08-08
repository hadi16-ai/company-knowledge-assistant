"""Hybrid (dense + keyword) retrieval backed by the organization's Qdrant collection.

Dense vector search alone misses exact-term matches — a policy number, an
ISO clause, a product code — that a keyword search finds instantly. This
module runs dense (semantic) and sparse (BM25 keyword) search as two
independent branches, merges them with Reciprocal Rank Fusion (RRF) so
scores from the two different scales don't need to be compared directly,
then reranks the merged candidate set with a cross-encoder for the final
ordering. See ARCHITECTURE_REVIEW.md §4/§8.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingConfigError, get_embeddings
from app.rag.reranker import rerank
from app.rag.vectorstore import collection_name_for_org, get_qdrant_client, scroll_all_documents


class RetrievalError(Exception):
    """Raised when a semantic search cannot be completed."""


@dataclass(frozen=True)
class RetrievedDocument:
    """A document chunk and its relevance score."""

    document: Document
    score: float


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

# How many candidates each retrieval branch contributes before RRF merge and
# reranking — wider than the final top-k so the cross-encoder has real
# signal to work with instead of re-sorting an already-narrow list.
_CANDIDATE_K = 20
_RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _dense_search(query: str, org_id: uuid.UUID, limit: int) -> list[tuple[str, Document]]:
    """Dense vector (semantic) search via Qdrant, ranked best-first."""
    client = get_qdrant_client()
    query_vector = get_embeddings().embed_query(query)
    response = client.query_points(
        collection_name=collection_name_for_org(org_id),
        query=query_vector,
        limit=limit,
        with_payload=True,
    )
    results: list[tuple[str, Document]] = []
    for point in response.points:
        payload = point.payload or {}
        document = Document(page_content=payload.get("page_content", ""), metadata=payload.get("metadata", {}))
        results.append((str(point.id), document))
    return results


def _sparse_search(query: str, org_id: uuid.UUID, limit: int) -> list[tuple[str, Document]]:
    """Keyword (BM25) search over every chunk in the organization's collection, ranked best-first."""
    corpus = scroll_all_documents(get_qdrant_client(), org_id)
    if not corpus:
        return []

    tokenized_corpus = [_tokenize(document.page_content) for _, document in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))

    ranked_indices = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    return [corpus[i] for i in ranked_indices[:limit] if scores[i] > 0]


def _reciprocal_rank_fusion(
    dense: list[tuple[str, Document]],
    sparse: list[tuple[str, Document]],
) -> list[tuple[Document, float]]:
    """Merge dense + sparse rankings by Reciprocal Rank Fusion.

    RRF rewards chunks that rank highly in *either* branch without needing
    the two branches' raw scores (cosine similarity vs. BM25) to be on a
    comparable scale — only rank position matters.
    """
    fused_scores: dict[str, float] = {}
    documents_by_id: dict[str, Document] = {}
    for ranked_list in (dense, sparse):
        for rank, (point_id, document) in enumerate(ranked_list):
            fused_scores[point_id] = fused_scores.get(point_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            documents_by_id.setdefault(point_id, document)

    ordered_ids = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
    return [(documents_by_id[point_id], score) for point_id, score in ordered_ids]


def retrieve_documents(query: str, org_id: uuid.UUID, k: int | None = None) -> list[RetrievedDocument]:
    """
    Retrieve the most relevant chunks for a user question within one org.

    Runs dense and BM25 keyword search in parallel branches, merges them via
    Reciprocal Rank Fusion, then reranks the merged candidate set with a
    cross-encoder before returning the final top-k.
    """
    normalized_query = query.strip()
    if not normalized_query:
        raise RetrievalError("Please enter a question before searching.")

    top_k = k or get_settings().retrieval_top_k
    if top_k < 1:
        raise RetrievalError("Retrieval count must be at least one.")

    try:
        dense_results = _dense_search(normalized_query, org_id, _CANDIDATE_K)
        sparse_results = _sparse_search(normalized_query, org_id, _CANDIDATE_K)
    except EmbeddingConfigError as exc:
        raise RetrievalError(str(exc)) from exc
    except Exception as exc:
        raise RetrievalError(f"Hybrid search failed: {exc}") from exc

    if not dense_results and not sparse_results:
        return []

    fused = _reciprocal_rank_fusion(dense_results, sparse_results)
    reranked = rerank(normalized_query, fused, top_k=top_k)

    return [
        RetrievedDocument(document=document, score=max(0.0, min(1.0, float(score))))
        for document, score in reranked
    ]
