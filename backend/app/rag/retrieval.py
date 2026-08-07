"""Semantic retrieval utilities backed by the organization's Qdrant collection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langchain_core.documents import Document

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingConfigError, get_embeddings
from app.rag.vectorstore import get_vectorstore


class RetrievalError(Exception):
    """Raised when a semantic search cannot be completed."""


@dataclass(frozen=True)
class RetrievedDocument:
    """A document chunk and its relevance score."""

    document: Document
    score: float


def retrieve_documents(query: str, org_id: uuid.UUID, k: int | None = None) -> list[RetrievedDocument]:
    """Retrieve the most semantically relevant chunks for a user question within one org."""
    normalized_query = query.strip()
    if not normalized_query:
        raise RetrievalError("Please enter a question before searching.")

    top_k = k or get_settings().retrieval_top_k
    if top_k < 1:
        raise RetrievalError("Retrieval count must be at least one.")

    try:
        vectorstore = get_vectorstore(get_embeddings(), org_id)
        matches = vectorstore.similarity_search_with_score(normalized_query, k=top_k)
    except EmbeddingConfigError as exc:
        raise RetrievalError(str(exc)) from exc
    except Exception as exc:
        raise RetrievalError(f"Semantic search failed: {exc}") from exc

    return [
        RetrievedDocument(document=document, score=max(0.0, min(1.0, float(score))))
        for document, score in matches
    ]
