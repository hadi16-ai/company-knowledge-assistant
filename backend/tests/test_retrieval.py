"""Unit tests for hybrid retrieval's pure merge/tokenize logic (no live Qdrant needed)."""

from __future__ import annotations

from langchain_core.documents import Document

from app.rag.retrieval import _reciprocal_rank_fusion, _tokenize


def test_tokenize_lowercases_and_strips_punctuation():
    assert _tokenize("ISO 9001:2015, Clause 8.4!") == ["iso", "9001", "2015", "clause", "8", "4"]


def test_tokenize_empty_string_returns_empty_list():
    assert _tokenize("") == []


def test_rrf_ranks_documents_in_both_lists_highest():
    doc_a = Document(page_content="a")
    doc_b = Document(page_content="b")
    doc_c = Document(page_content="c")

    # "a" ranks #1 in both branches; "b" only in dense; "c" only in sparse.
    dense = [("a", doc_a), ("b", doc_b)]
    sparse = [("a", doc_a), ("c", doc_c)]

    fused = _reciprocal_rank_fusion(dense, sparse)

    assert fused[0][0] is doc_a
    fused_ids = {id(doc) for doc, _ in fused}
    assert id(doc_b) in fused_ids
    assert id(doc_c) in fused_ids


def test_rrf_deduplicates_by_point_id():
    doc_a = Document(page_content="a")
    dense = [("a", doc_a)]
    sparse = [("a", doc_a)]

    fused = _reciprocal_rank_fusion(dense, sparse)

    assert len(fused) == 1


def test_rrf_empty_inputs_returns_empty():
    assert _reciprocal_rank_fusion([], []) == []
