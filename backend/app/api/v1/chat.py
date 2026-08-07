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
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db.models import QueryLog
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.rag.rag import AnswerGenerationError, retrieve_context, stream_answer_tokens
from app.schemas.chat import AskRequest, AskResponse, SourceCitationResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/ask")
def ask(
    payload: AskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Answer a question grounded in the org's indexed documents, streamed via SSE."""
    started_at = time.monotonic()

    try:
        context, sources = retrieve_context(payload.question, current_user.org_id)
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    def event_stream():
        yield _sse_event("sources", {"sources": [asdict(s) for s in sources]})

        full_answer_parts: list[str] = []
        try:
            for token in stream_answer_tokens(payload.question, context):
                full_answer_parts.append(token)
                yield _sse_event("token", {"text": token})
        except AnswerGenerationError as exc:
            yield _sse_event("error", {"message": str(exc)})
            return

        full_answer = "".join(full_answer_parts).strip()
        latency_ms = int((time.monotonic() - started_at) * 1000)

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
    context, sources = retrieve_context(payload.question, current_user.org_id)

    answer_parts = list(stream_answer_tokens(payload.question, context))
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
