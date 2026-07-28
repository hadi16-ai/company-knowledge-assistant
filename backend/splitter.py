"""Text splitting utilities for document chunking."""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Return a configured RecursiveCharacterTextSplitter instance."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )


def split_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into smaller chunks for embedding.

    Args:
        documents: Loaded page-level documents.

    Returns:
        List of chunked documents with preserved metadata.
    """
    splitter = get_text_splitter()
    return splitter.split_documents(documents)
