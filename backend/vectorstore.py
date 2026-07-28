"""ChromaDB vector store utilities."""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from backend.utils import CHROMA_DIR, COLLECTION_NAME


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""


def get_vectorstore(embeddings: Embeddings) -> Chroma:
    """
    Return a persistent Chroma vector store instance.

    Args:
        embeddings: Embeddings client used for indexing.

    Returns:
        Persistent Chroma vector store.
    """
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def is_document_indexed(vectorstore: Chroma, source_filename: str) -> bool:
    """
    Check whether chunks from a given source file are already indexed.

    Args:
        vectorstore: Active Chroma vector store.
        source_filename: Original PDF filename stored in document metadata.

    Returns:
        True if at least one chunk exists for the source file.
    """
    try:
        results = vectorstore.get(where={"source": source_filename}, limit=1)
        return bool(results.get("ids"))
    except Exception:
        return False


def add_documents_to_store(
    vectorstore: Chroma,
    documents: list[Document],
) -> list[str]:
    """
    Add document chunks to the vector store.

    Args:
        vectorstore: Active Chroma vector store.
        documents: Chunked documents to embed and store.

    Returns:
        List of inserted document IDs.

    Raises:
        VectorStoreError: If documents cannot be stored.
    """
    try:
        return vectorstore.add_documents(documents)
    except Exception as exc:
        raise VectorStoreError(f"Failed to store documents in ChromaDB: {exc}") from exc


def get_indexed_document_count(vectorstore: Chroma) -> int:
    """Return the total number of indexed chunks in the collection."""
    try:
        return vectorstore._collection.count()
    except Exception:
        return 0


def get_indexed_sources(vectorstore: Chroma) -> set[str]:
    """Return unique source filenames currently indexed in the vector store."""
    try:
        results = vectorstore.get(include=["metadatas"])
        metadatas = results.get("metadatas") or []
        return {
            metadata.get("source", "")
            for metadata in metadatas
            if metadata and metadata.get("source")
        }
    except Exception:
        return set()
