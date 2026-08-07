"""Unit tests for document chunking."""

from __future__ import annotations

from langchain_core.documents import Document

from app.rag.splitter import CHUNK_OVERLAP, CHUNK_SIZE, split_documents


def test_split_documents_preserves_metadata():
    long_text = "Sentence about company policy. " * 100
    docs = [Document(page_content=long_text, metadata={"source": "policy.pdf", "page": 0})]

    chunks = split_documents(docs)

    assert len(chunks) > 1
    assert all(chunk.metadata["source"] == "policy.pdf" for chunk in chunks)
    assert all(len(chunk.page_content) <= CHUNK_SIZE for chunk in chunks)


def test_split_documents_empty_input_returns_empty():
    assert split_documents([]) == []


def test_chunk_overlap_smaller_than_chunk_size():
    assert CHUNK_OVERLAP < CHUNK_SIZE
