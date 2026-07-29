"""Semantic retrieval utilities backed by the existing ChromaDB collection."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document

from backend.embeddings import EmbeddingConfigError, get_embeddings
from backend.vectorstore import get_vectorstore

DEFAULT_RETRIEVAL_K = 4


class RetrievalError(Exception):
    """Raised when a semantic search cannot be completed."""


@dataclass(frozen=True)
class RetrievedDocument:
    """A document chunk and its relevance score."""

    document: Document
    score: float


def retrieve_documents(query: str, k: int = DEFAULT_RETRIEVAL_K) -> list[RetrievedDocument]:
    """Retrieve the most semantically relevant chunks for a user question."""
    normalized_query = query.strip()
    if not normalized_query:
        raise RetrievalError("Please enter a question before searching.")
    if k < 1:
        raise RetrievalError("Retrieval count must be at least one.")

    try:
        # Ingestion and retrieval intentionally share this model and collection.
        vectorstore = get_vectorstore(get_embeddings())
        matches = vectorstore.similarity_search_with_relevance_scores(normalized_query, k=k)
    except EmbeddingConfigError as exc:
        raise RetrievalError(str(exc)) from exc
    except Exception as exc:
        raise RetrievalError(f"Semantic search failed: {exc}") from exc

    return [
        RetrievedDocument(document=document, score=max(0.0, min(1.0, float(score))))
        for document, score in matches
    ]
