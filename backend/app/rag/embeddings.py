"""Local Hugging Face embedding utilities."""

from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import get_settings


class EmbeddingConfigError(Exception):
    """Raised when embedding configuration is invalid."""


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Create and return a cached local Hugging Face embeddings client.

    Returns:
        Configured HuggingFaceEmbeddings instance.

    Raises:
        EmbeddingConfigError: If the embedding model cannot be initialized.
    """
    model_name = get_settings().embedding_model
    try:
        return HuggingFaceEmbeddings(model_name=model_name)
    except Exception as exc:
        raise EmbeddingConfigError(
            f"Failed to initialize embedding model '{model_name}': {exc}"
        ) from exc


def validate_embeddings_connection() -> None:
    """
    Verify that embeddings can be generated with the current configuration.

    Raises:
        EmbeddingConfigError: If the embedding model cannot be initialized.
        EmbeddingError: If a test embedding request fails.
    """
    embeddings = get_embeddings()
    try:
        embeddings.embed_query("connectivity check")
    except Exception as exc:
        raise EmbeddingError(f"Embedding request failed: {exc}") from exc
