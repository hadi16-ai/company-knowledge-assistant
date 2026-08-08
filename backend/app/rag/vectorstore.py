"""Qdrant vector store utilities.

Replaces the v1 ChromaDB store. Each organization gets its own Qdrant
collection (``{prefix}_{org_id}``) so tenant isolation happens at the
collection level, not just via a payload filter — per architecture review
§7, collection names are never exposed to the frontend and are derived
server-side from the authenticated user's ``org_id``.
"""

from __future__ import annotations

import uuid

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import get_settings

EMBEDDING_DIMENSIONS = 384  # BAAI/bge-small-en-v1.5


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""


def collection_name_for_org(org_id: uuid.UUID) -> str:
    """Return the Qdrant collection name for an organization (never exposed to the frontend)."""
    prefix = get_settings().qdrant_collection_prefix
    return f"{prefix}_{org_id}"


def get_qdrant_client() -> QdrantClient:
    """Return a Qdrant client configured from application settings."""
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection(client: QdrantClient, org_id: uuid.UUID) -> str:
    """Create the organization's Qdrant collection if it does not exist yet."""
    collection_name = collection_name_for_org(org_id)
    try:
        client.get_collection(collection_name)
    except (UnexpectedResponse, ValueError):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=EMBEDDING_DIMENSIONS, distance=qmodels.Distance.COSINE
            ),
        )
    return collection_name


def get_vectorstore(embeddings: Embeddings, org_id: uuid.UUID) -> QdrantVectorStore:
    """
    Return a Qdrant-backed vector store scoped to one organization.

    Args:
        embeddings: Embeddings client used for indexing and querying.
        org_id: Organization the collection belongs to.

    Returns:
        A QdrantVectorStore bound to the organization's collection.
    """
    client = get_qdrant_client()
    collection_name = ensure_collection(client, org_id)
    return QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
    )


def is_document_indexed(client: QdrantClient, org_id: uuid.UUID, source_filename: str) -> bool:
    """Check whether chunks from a given source file are already indexed."""
    collection_name = collection_name_for_org(org_id)
    try:
        result, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="metadata.source", match=qmodels.MatchValue(value=source_filename))]
            ),
            limit=1,
        )
        return bool(result)
    except (UnexpectedResponse, ValueError):
        return False


def add_documents_to_store(
    vectorstore: QdrantVectorStore,
    documents: list[Document],
    org_id: uuid.UUID,
    doc_id: uuid.UUID,
) -> list[str]:
    """
    Embed and store document chunks, stamping org/document identifiers onto each.

    Args:
        vectorstore: Active QdrantVectorStore for the organization.
        documents: Chunked documents to embed and store.
        org_id: Owning organization, stamped into payload for defense-in-depth filtering.
        doc_id: Document registry id these chunks belong to.

    Returns:
        List of inserted point IDs.

    Raises:
        VectorStoreError: If documents cannot be stored.
    """
    for document in documents:
        document.metadata["org_id"] = str(org_id)
        document.metadata["doc_id"] = str(doc_id)

    try:
        return vectorstore.add_documents(documents)
    except Exception as exc:
        raise VectorStoreError(f"Failed to store documents in Qdrant: {exc}") from exc


def get_indexed_document_count(client: QdrantClient, org_id: uuid.UUID) -> int:
    """Return the total number of indexed chunks in the organization's collection."""
    try:
        info = client.get_collection(collection_name_for_org(org_id))
        return info.points_count or 0
    except (UnexpectedResponse, ValueError):
        return 0


def scroll_all_documents(client: QdrantClient, org_id: uuid.UUID, limit: int = 10_000) -> list[tuple[str, Document]]:
    """Return every chunk in the organization's collection as (point_id, Document) pairs.

    Used to build the in-memory BM25 index for hybrid search — Qdrant's
    open-source tier has no native BM25/full-text ranking, so keyword search
    runs client-side over each org's chunk corpus. This scales comfortably to
    the tens-of-thousands-of-chunks range; a much larger single-org corpus
    would warrant a real sparse-vector or external search index instead.
    """
    collection_name = collection_name_for_org(org_id)
    results: list[tuple[str, Document]] = []
    next_offset = None
    try:
        while True:
            batch_limit = min(limit - len(results), 1000) if limit else 1000
            if batch_limit <= 0:
                break
            points, next_offset = client.scroll(
                collection_name=collection_name,
                limit=batch_limit,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                content = payload.get("page_content", "")
                metadata = payload.get("metadata", {})
                results.append((str(point.id), Document(page_content=content, metadata=metadata)))
            if next_offset is None:
                break
    except (UnexpectedResponse, ValueError):
        return []
    return results


def delete_document_chunks(client: QdrantClient, org_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    """Delete every chunk belonging to one document from the organization's collection.

    Used before re-indexing or replacing a document, and when deleting a
    document outright, so stale vectors never linger and get retrieved
    alongside (or instead of) the current content.
    """
    try:
        client.delete(
            collection_name=collection_name_for_org(org_id),
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="metadata.doc_id", match=qmodels.MatchValue(value=str(doc_id)))]
                )
            ),
        )
    except (UnexpectedResponse, ValueError) as exc:
        raise VectorStoreError(f"Failed to delete existing chunks for document {doc_id}: {exc}") from exc
