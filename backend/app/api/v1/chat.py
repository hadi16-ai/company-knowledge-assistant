"""Chat / Q&A endpoint with Server-Sent Events streaming.

Streams the answer token-by-token (architecture review §5, "Chat Interface —
the most important screen": answers should appear word by word, not after a
multi-second wait) and logs every query to `query_log` for the audit trail
and future analytics (§3, §11).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db.base import SessionLocal
from app.db.models import QueryLog
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.rag.rag import AnswerGenerationError, ConversationTurn, retrieve_context, stream_answer_tokens
from app.schemas.chat import (
    AskRequest,
    AskResponse,
    ConversationTurnRequest,
    QueryLogEntry,
    SourceCitationResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# How many past turns to restore when a user returns to /chat. Generous enough to feel like
# a real history without unbounded growth; unrelated to conversation_memory_turns, which caps
# what's actually folded into the LLM prompt for a given request.
HISTORY_RESTORE_LIMIT = 50


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _to_conversation_history(turns: list[ConversationTurnRequest]) -> list[ConversationTurn]:
    return [ConversationTurn(role=turn.role, content=turn.content) for turn in turns]


@router.get("/history", response_model=list[QueryLogEntry])
def get_history(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QueryLog]:
    """Return the caller's recent turns, oldest first, to restore their chat on load.

    Scoped to org_id and user_id from the JWT (never a request parameter) so one
    user's history can never leak into another's, matching the IDOR-safety pattern
    used across the rest of the API (see ARCHITECTURE_REVIEW.md §6).
    """
    rows = list(
        db.execute(
            select(QueryLog)
            .where(QueryLog.org_id == current_user.org_id, QueryLog.user_id == current_user.id)
            .order_by(QueryLog.created_at.desc())
            .limit(HISTORY_RESTORE_LIMIT)
        ).scalars()
    )
    return list(reversed(rows))


@router.post("/ask")
def ask(
    payload: AskRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Answer a question grounded in the org's indexed documents, streamed via SSE."""
    started_at = time.monotonic()
    history = _to_conversation_history(payload.history)

    try:
        context, sources = retrieve_context(payload.question, current_user.org_id, history)
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    def event_stream():
        yield _sse_event("sources", {"sources": [asdict(s) for s in sources]})

        full_answer_parts: list[str] = []
        try:
            for token in stream_answer_tokens(payload.question, context, history):
                full_answer_parts.append(token)
                yield _sse_event("token", {"text": token})
        except AnswerGenerationError as exc:
            yield _sse_event("error", {"message": str(exc)})
            return

        full_answer = "".join(full_answer_parts).strip()
        latency_ms = int((time.monotonic() - started_at) * 1000)

        # A request-scoped `Depends(get_db)` session would already be closed by the time
        # this code runs: FastAPI tears down dependencies as soon as the route handler
        # returns the StreamingResponse object, which happens before Starlette actually
        # starts iterating this generator. Open a session scoped to the generator's own
        # lifetime instead, so the persisted turn survives regardless of how long
        # streaming took (this was silently dropping turns before this fix).
        db = SessionLocal()
        try:
            db.add(
                QueryLog(
                    id=uuid.uuid4(),
                    org_id=current_user.org_id,
                    user_id=current_user.id,
                    query=payload.question,
                    answer=full_answer,
                    latency_ms=latency_ms,
                )
            )
            db.commit()
        finally:
            db.close()

        yield _sse_event("done", {"answer": full_answer, "latency_ms": latency_ms})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/ask-sync", response_model=AskResponse)
def ask_sync(
    payload: AskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    """Non-streaming variant of /ask, kept for simple integrations and tests."""
    started_at = time.monotonic()
    history = _to_conversation_history(payload.history)
    context, sources = retrieve_context(payload.question, current_user.org_id, history)

    answer_parts = list(stream_answer_tokens(payload.question, context, history))
    answer_text = "".join(answer_parts).strip()
    if not answer_text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini returned an empty answer.")

    latency_ms = int((time.monotonic() - started_at) * 1000)
    db.add(
        QueryLog(
            id=uuid.uuid4(),
            org_id=current_user.org_id,
            user_id=current_user.id,
            query=payload.question,
            answer=answer_text,
            latency_ms=latency_ms,
        )
    )
    db.commit()

    return AskResponse(
        answer=answer_text,
        sources=[SourceCitationResponse(**asdict(s)) for s in sources],
    )
