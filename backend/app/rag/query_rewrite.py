"""Conversational query rewriting.

Turns a follow-up message ("What about last year?") into a self-contained
retrieval query ("What was the leave policy last year?") using the existing
conversation history, before hybrid retrieval runs. This only changes what
string retrieval searches with — the original question is untouched and is
still what gets sent to answer generation, the UI, and `query_log` (see
`app.rag.rag.retrieve_context` / `app.api.v1.chat`), so a hallucinated
rewrite can only ever steer *which chunks get retrieved*, never appear in
the answer the user reads.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.rag.rag import ConversationTurn

logger = logging.getLogger(__name__)

# Above this, treat the model's output as unusable rather than risk feeding a
# runaway/garbled generation into retrieval.
MAX_REWRITE_CHARS = 500

REWRITE_SYSTEM_INSTRUCTIONS = (
    "You rewrite a user's latest chat message into a standalone search query for a "
    "document-retrieval system, using only the conversation already shown to you.\n\n"
    "Resolve pronouns and omitted context using the conversation — for example, "
    '"What about last year?" following a question about a leave policy becomes '
    '"What was the leave policy last year?"\n\n'
    "Never introduce facts, dates, names, or details that are not already present in "
    "the conversation. If the latest message is already a self-contained question, "
    "return it unchanged. Reply with the rewritten query only — no explanation, no "
    "quotes, no preamble."
)


class QueryRewriteError(Exception):
    """Raised when the rewrite model cannot be reached."""


@lru_cache
def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise QueryRewriteError(
            "GEMINI_API_KEY is not configured. Add a newly generated key to the server-side deployment secrets."
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _has_resolvable_history(history: list[ConversationTurn]) -> bool:
    """Only bother calling the rewrite model when there's a prior user turn to resolve against."""
    return any(turn.role == "user" for turn in history)


def _build_rewrite_prompt(question: str, history: list[ConversationTurn]) -> str:
    transcript = "\n".join(f"{turn.role.capitalize()}: {turn.content.strip()}" for turn in history)
    return f"Conversation so far (most recent last):\n{transcript}\n\nLatest message to rewrite:\n{question.strip()}"


def rewrite_query(question: str, history: list[ConversationTurn]) -> str:
    """
    Rewrite `question` into a standalone retrieval query using prior turns.

    Falls back to returning `question` unchanged whenever the rewrite can't
    be trusted: no history to resolve against, the model is unreachable, the
    call fails, or the output is empty/oversized — retrieval always gets
    *some* usable query, and a rewrite failure never blocks answering.
    """
    normalized = question.strip()
    if not normalized or not _has_resolvable_history(history):
        return question

    try:
        client = _get_client()
    except QueryRewriteError as exc:
        logger.warning("Query rewrite unavailable, using the original question: %s", exc)
        return question

    try:
        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=_build_rewrite_prompt(normalized, history),
            config=types.GenerateContentConfig(
                system_instruction=REWRITE_SYSTEM_INSTRUCTIONS,
                temperature=0.0,
                max_output_tokens=200,
            ),
        )
        rewritten = (response.text or "").strip().strip('"')
    except Exception as exc:
        logger.warning("Query rewrite failed, falling back to the original question: %s", exc)
        return question

    if not rewritten or len(rewritten) > MAX_REWRITE_CHARS:
        return question

    logger.debug("Rewrote retrieval query %r -> %r", question, rewritten)
    return rewritten
