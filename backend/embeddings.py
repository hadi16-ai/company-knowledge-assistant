"""Local Hugging Face embedding utilities."""

from __future__ import annotations

from langchain_huggingface import HuggingFaceEmbeddings

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


class EmbeddingConfigError(Exception):
    """Raised when embedding configuration is invalid."""


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Create and return a local Hugging Face embeddings client.

    Returns:
        Configured HuggingFaceEmbeddings instance.

    Raises:
        EmbeddingConfigError: If the embedding model cannot be initialized.
    """
    try:
        return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    except Exception as exc:
        raise EmbeddingConfigError(
            f"Failed to initialize embedding model '{EMBEDDING_MODEL}': {exc}"
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
