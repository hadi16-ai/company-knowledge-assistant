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
from app.rag.query_rewrite import rewrite_query
from app.rag.retrieval import RetrievalError, retrieve_documents

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = (
    "You are the Company Knowledge Assistant, an enterprise AI that helps employees "
    "understand company documents.\n\n"
    "Ground every answer strictly in the supplied company-document context — never "
    "invent facts, figures, policies, or sources that aren't present in it. If the "
    "context does not answer the question, say so plainly instead of guessing.\n\n"
    "When the context gives you enough to work with, answer thoroughly rather than "
    "tersely:\n"
    "- Use short Markdown headings (##) to organize multi-part answers.\n"
    "- Write in complete paragraphs that explain the 'why', not clipped one-liners.\n"
    "- Use bullet or numbered lists for steps, criteria, or enumerated items.\n"
    "- Reference sources inline with labels like [Source 1] so claims stay traceable.\n\n"
    "Match the depth of the answer to the depth of the question and what the context "
    "actually supports — a simple factual question still deserves a direct, short "
    "answer rather than padding."
)


class AnswerGenerationError(Exception):
    """Raised when a grounded answer cannot be generated."""


@dataclass(frozen=True)
class RAGAnswer:
    """A generated answer and its supporting retrieved sources."""

    text: str
    sources: list[SourceCitation]


@dataclass(frozen=True)
class ConversationTurn:
    """One prior turn in the ongoing chat, used to give the assistant short-term memory."""

    role: str  # "user" | "assistant"
    content: str


def _recent_history(history: list[ConversationTurn] | None) -> list[ConversationTurn]:
    """Clamp history to the configured memory window regardless of what the caller sent."""
    if not history:
        return []
    max_messages = get_settings().conversation_memory_turns * 2
    return history[-max_messages:]


def retrieve_context(
    question: str,
    org_id: uuid.UUID,
    history: list[ConversationTurn] | None = None,
) -> tuple[str, list[SourceCitation]]:
    """Retrieve relevant chunks for an org and build bounded, citable context.

    The question is rewritten into a standalone retrieval query first (folding
    in conversation history so follow-ups like "what about last year?" resolve
    to something searchable) — see `app.rag.query_rewrite`. Only the retrieval
    *query* changes; `question` itself still flows on unchanged to answer
    generation, so a bad rewrite can degrade which chunks get retrieved but
    can never itself become a fact in the answer.
    """
    settings = get_settings()
    recent_history = _recent_history(history)
    retrieval_query = rewrite_query(question, recent_history)
    try:
        matches = retrieve_documents(retrieval_query, org_id, k=settings.retrieval_top_k)
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
            "GEMINI_API_KEY is not configured. Add a newly generated key to the server-side deployment secrets to enable answers."
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _build_prompt(question: str, context: str, history: list[ConversationTurn] | None = None) -> str:
    recent_history = _recent_history(history)
    parts: list[str] = []
    if recent_history:
        transcript = "\n".join(f"{turn.role.capitalize()}: {turn.content.strip()}" for turn in recent_history)
        parts.append(f"Conversation so far (most recent last):\n{transcript}")
    parts.append(f"Question:\n{question.strip()}")
    parts.append(f"Company-document context:\n{context}")
    return "\n\n".join(parts)


def _generation_config() -> types.GenerateContentConfig:
    settings = get_settings()
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=settings.gemini_temperature,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


def answer_question(
    question: str,
    org_id: uuid.UUID,
    history: list[ConversationTurn] | None = None,
) -> RAGAnswer:
    """Retrieve relevant chunks and generate a complete (non-streaming) grounded answer."""
    context, sources = retrieve_context(question, org_id, history)
    settings = get_settings()
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=_build_prompt(question, context, history),
            config=_generation_config(),
        )
        answer_text = (response.text or "").strip()
    except Exception as exc:
        logger.exception("Gemini generation failed")
        raise AnswerGenerationError(f"Answer generation failed: {exc}") from exc

    if not answer_text:
        raise AnswerGenerationError("Gemini returned an empty answer.")

    return RAGAnswer(text=answer_text, sources=sources)


def stream_answer_tokens(
    question: str,
    context: str,
    history: list[ConversationTurn] | None = None,
) -> Iterator[str]:
    """Yield answer text incrementally as Gemini streams its response."""
    settings = get_settings()
    client = _get_client()
    try:
        for chunk in client.models.generate_content_stream(
            model=settings.gemini_model,
            contents=_build_prompt(question, context, history),
            config=_generation_config(),
        ):
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        logger.exception("Gemini streaming generation failed")
        raise AnswerGenerationError(f"Answer generation failed: {exc}") from exc
