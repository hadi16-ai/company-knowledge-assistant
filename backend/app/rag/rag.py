"""Gemini answer generation via the official google-genai SDK.

Replaces v1's raw ``urllib`` HTTP calls: the SDK gives retry handling,
typed exceptions, and native streaming for free (architecture review §1/§2).
Uses ``google-genai`` (not the end-of-life ``google-generativeai`` package).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.rag.context import SourceCitation, build_context
from app.rag.retrieval import RetrievalError, retrieve_documents

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = (
    "You are the Company Knowledge Assistant. "
    "Answer only from the supplied company-document context. "
    "If the context does not answer the question, say that clearly. "
    "Do not invent facts or cite sources not provided. "
    "Keep the answer concise and use source labels such as [Source 1] when helpful."
)


class AnswerGenerationError(Exception):
    """Raised when a grounded answer cannot be generated."""


@dataclass(frozen=True)
class RAGAnswer:
    """A generated answer and its supporting retrieved sources."""

    text: str
    sources: list[SourceCitation]


def retrieve_context(question: str, org_id: uuid.UUID) -> tuple[str, list[SourceCitation]]:
    """Retrieve relevant chunks for an org and build bounded, citable context."""
    settings = get_settings()
    try:
        matches = retrieve_documents(question, org_id, k=settings.retrieval_top_k)
    except RetrievalError as exc:
        raise AnswerGenerationError(str(exc)) from exc

    if not matches:
        raise AnswerGenerationError(
            "No relevant indexed content was found. Upload and process company documents first."
        )

    context, sources = build_context(matches, settings.max_context_characters)
    if not context:
        raise AnswerGenerationError("The retrieved documents did not contain readable text.")

    return context, sources


@lru_cache
def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AnswerGenerationError(
            "GEMINI_API_KEY is not configured. Add it to .env to enable answers."
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _build_prompt(question: str, context: str) -> str:
    return f"Question:\n{question.strip()}\n\nCompany-document context:\n{context}"


def _generation_config() -> types.GenerateContentConfig:
    settings = get_settings()
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=settings.gemini_temperature,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


def answer_question(question: str, org_id: uuid.UUID) -> RAGAnswer:
    """Retrieve relevant chunks and generate a complete (non-streaming) grounded answer."""
    context, sources = retrieve_context(question, org_id)
    settings = get_settings()
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=_build_prompt(question, context),
            config=_generation_config(),
        )
        answer_text = (response.text or "").strip()
    except Exception as exc:
        logger.exception("Gemini generation failed")
        raise AnswerGenerationError(f"Answer generation failed: {exc}") from exc

    if not answer_text:
        raise AnswerGenerationError("Gemini returned an empty answer.")

    return RAGAnswer(text=answer_text, sources=sources)


def stream_answer_tokens(question: str, context: str) -> Iterator[str]:
    """Yield answer text incrementally as Gemini streams its response."""
    settings = get_settings()
    client = _get_client()
    try:
        for chunk in client.models.generate_content_stream(
            model=settings.gemini_model,
            contents=_build_prompt(question, context),
            config=_generation_config(),
        ):
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        logger.exception("Gemini streaming generation failed")
        raise AnswerGenerationError(f"Answer generation failed: {exc}") from exc
