"""Context construction for retrieval-augmented generation."""

from __future__ import annotations

from dataclasses import dataclass

from backend.retrieval import RetrievedDocument

MAX_CONTEXT_CHARACTERS = 12_000


@dataclass(frozen=True)
class SourceCitation:
    """A user-facing citation for a retrieved PDF chunk."""

    filename: str
    page_number: int | None
    excerpt: str
    score: float


def _page_number(metadata: dict) -> int | None:
    """Convert zero-based PyPDFLoader metadata into a display page number."""
    page = metadata.get("page")
    if isinstance(page, int):
        return page + 1
    if isinstance(page, str) and page.isdigit():
        return int(page) + 1
    return None


def build_context(matches: list[RetrievedDocument]) -> tuple[str, list[SourceCitation]]:
    """Build bounded, labeled RAG context and citations from retrieved chunks."""
    context_parts: list[str] = []
    citations: list[SourceCitation] = []
    used_characters = 0
    for index, match in enumerate(matches, start=1):
        metadata = match.document.metadata or {}
        filename = str(metadata.get("source") or "Unknown document")
        page_number = _page_number(metadata)
        page_label = f", page {page_number}" if page_number is not None else ""
        content = match.document.page_content.strip()
        if not content:
            continue
        remaining = MAX_CONTEXT_CHARACTERS - used_characters
        if remaining <= 0:
            break
        content = content[:remaining]
        context_parts.append(f"[Source {index}: {filename}{page_label}]\n{content}")
        citations.append(SourceCitation(filename, page_number, content, match.score))
        used_characters += len(content)
    return "\n\n".join(context_parts), citations
