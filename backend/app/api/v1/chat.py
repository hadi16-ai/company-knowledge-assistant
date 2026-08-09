"""Chat / Q&A endpoint with Server-Sent Events streaming.

Streams the answer token-by-token (architecture review §5, "Chat Interface —
the most important screen": answers should appear word by word, not after a
multi-second wait) and logs every query to `query_log` for the audit trail
and future analytics (§3, §11).

Conversation memory is scoped to a specific `Conversation` (see
`app.api.v1.conversations`): every request names the thread it belongs to
via `conversation_id`, history is loaded server-side from that thread's own
`query_log` rows (never trusted from client-submitted content), and
`get_owned_conversation` 404s outright if the id doesn't belong to the
caller's own org+user. This is what makes query rewriting (`app.rag.rag`)
conversation-scoped for free — it only ever sees the turns this endpoint
hands it.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.v1.conversations import generate_conversation_title, get_owned_conversation
from app.core.config import get_settings
from app.db.base import SessionLocal
from app.db.models import Conversation, QueryLog
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.rag.rag import AnswerGenerationError, ConversationTurn, retrieve_context, stream_answer_tokens
from app.schemas.chat import AskRequest, AskResponse, SourceCitationResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _load_recent_turns(db: Session, conversation_id: uuid.UUID, limit: int) -> list[ConversationTurn]:
    """Load a conversation's most recent turns, oldest first, as ConversationTurn pairs.

    Each query_log row is one exchange (one user turn + one assistant turn),
    so limiting to `limit` rows caps the *pairs* — matching how
    `app.rag.rag._recent_history` already interprets `conversation_memory_turns`.
    """
    rows = list(
        db.query(QueryLog)
        .filter(QueryLog.conversation_id == conversation_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    rows.reverse()
    turns: list[ConversationTurn] = []
    for row in rows:
        turns.append(ConversationTurn(role="user", content=row.query))
        turns.append(ConversationTurn(role="assistant", content=row.answer))
    return turns


def _record_turn(
    db: Session,
    conversation_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    answer: str,
    latency_ms: int,
) -> None:
    """Persist one turn and bump the owning conversation's title/updated_at.

    Re-fetches the Conversation in `db` rather than trusting a caller-passed
    ORM instance, since the streaming endpoint calls this from a
    generator-scoped session that outlives the request-scoped one the
    conversation was originally loaded in (see the comment in `ask()`).
    """
    db.add(
        QueryLog(
            id=uuid.uuid4(),
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
            query=question,
            answer=answer,
            latency_ms=latency_ms,
        )
    )
    conversation = db.get(Conversation, conversation_id)
    if conversation is not None:
        if conversation.title is None:
            conversation.title = generate_conversation_title(question)
        conversation.updated_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/ask")
def ask(
    payload: AskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Answer a question grounded in the org's indexed documents, streamed via SSE."""
    started_at = time.monotonic()
    conversation = get_owned_conversation(db, payload.conversation_id, current_user)
    history = _load_recent_turns(db, conversation.id, get_settings().conversation_memory_turns)
    conversation_id = conversation.id

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
        db_write = SessionLocal()
        try:
            _record_turn(
                db_write, conversation_id, current_user.org_id, current_user.id, payload.question, full_answer, latency_ms
            )
        finally:
            db_write.close()

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
    conversation = get_owned_conversation(db, payload.conversation_id, current_user)
    history = _load_recent_turns(db, conversation.id, get_settings().conversation_memory_turns)

    try:
        context, sources = retrieve_context(payload.question, current_user.org_id, history)
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    answer_parts = list(stream_answer_tokens(payload.question, context, history))
    answer_text = "".join(answer_parts).strip()
    if not answer_text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini returned an empty answer.")

    latency_ms = int((time.monotonic() - started_at) * 1000)
    _record_turn(db, conversation.id, current_user.org_id, current_user.id, payload.question, answer_text, latency_ms)

    return AskResponse(
        answer=answer_text,
        sources=[SourceCitationResponse(**asdict(s)) for s in sources],
    )
