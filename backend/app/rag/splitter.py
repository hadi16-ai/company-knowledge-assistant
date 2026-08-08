"""Text splitting utilities for document chunking.

Chunks are built structure-first (heading -> paragraph -> sentence) rather
than by raw character count, so a chunk boundary lands on a natural
document break instead of mid-sentence. See ARCHITECTURE_REVIEW.md §4.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# A line counts as a heading if it's short, has no terminal punctuation, and
# looks like a title (numbered, markdown-style, or Title/ALL-CAPS Case)
# rather than a sentence fragment that happens to sit alone on its line.
_HEADING_PATTERN = re.compile(
    r"^\s*(#{1,6}\s+.+|\d{1,2}[.)]\s+[A-Z].{0,100}|[A-Z][A-Za-z0-9 ,'&/-]{2,80})\s*$"
)

# Sentence boundaries are tried before the raw word-space fallback so an
# oversized paragraph still breaks between sentences before it breaks
# mid-sentence. LangChain's default separators stop at "\n"/" " and never
# try ". "/"! "/"? " at all.
_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]


def _merge_headings_into_following_paragraph(text: str) -> str:
    """Join a heading-like line to the paragraph beneath it.

    Prevents the splitter from ever isolating a bare heading into its own
    chunk, disconnected from the content it titles.
    """
    paragraphs = text.split("\n\n")
    merged: list[str] = []
    for para in paragraphs:
        stripped = para.strip()
        if merged and stripped and "\n" not in stripped and _HEADING_PATTERN.match(stripped):
            merged[-1] = f"{merged[-1]}\n\n{para}"
        else:
            merged.append(para)
    return "\n\n".join(merged)


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Return a splitter that prefers paragraph/sentence boundaries over raw character counts."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=_SEPARATORS,
    )


def split_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into semantically coherent chunks for embedding.

    Headings are merged into the paragraph they introduce before splitting,
    and the separator hierarchy prefers paragraph and sentence boundaries,
    so chunks read as complete thoughts rather than raw character windows.

    Args:
        documents: Loaded page-level documents.

    Returns:
        List of chunked documents with preserved metadata.
    """
    if not documents:
        return []

    prepared = [
        Document(page_content=_merge_headings_into_following_paragraph(doc.page_content), metadata=doc.metadata)
        for doc in documents
    ]
    splitter = get_text_splitter()
    return splitter.split_documents(prepared)
