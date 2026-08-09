"""Conversation/thread management: create, list, open, delete.

Every route is scoped to the caller's own `org_id` **and** `user_id` — a
conversation belongs to exactly one user in exactly one org (never just
org-wide), so listing/opening/deleting never accept an org or user id from
the request, matching the IDOR-safety pattern used everywhere else in this
API (see `app/deps.py`). `get_owned_conversation` is the single enforcement
point for that and is reused by `app.api.v1.chat` when loading a
conversation's history for `/chat/ask`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, QueryLog
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.schemas.conversations import ConversationMessage, ConversationResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])

TITLE_MAX_LENGTH = 60


def _conversation_is_owned_by(conversation: Conversation, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Pure ownership check — no DB access, unit-testable in isolation."""
    return conversation.org_id == org_id and conversation.user_id == user_id


def get_owned_conversation(db: Session, conversation_id: uuid.UUID, current_user: CurrentUser) -> Conversation:
    """Load a conversation, 404'ing unless it belongs to the caller's own org+user."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or not _conversation_is_owned_by(conversation, current_user.org_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


def generate_conversation_title(question: str, max_length: int = TITLE_MAX_LENGTH) -> str:
    """Derive a conversation title from its first question — no LLM call, purely deterministic."""
    normalized = " ".join(question.strip().split())
    if len(normalized) <= max_length:
        return normalized
    truncated = normalized[:max_length].rsplit(" ", 1)[0].rstrip()
    return f"{truncated or normalized[:max_length]}…"


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Start a new, empty conversation. Titled once the first question is asked."""
    conversation = Conversation(id=uuid.uuid4(), org_id=current_user.org_id, user_id=current_user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    """List the caller's own conversations, most recently active first."""
    return list(
        db.execute(
            select(Conversation)
            .where(Conversation.org_id == current_user.org_id, Conversation.user_id == current_user.id)
            .order_by(Conversation.updated_at.desc())
        ).scalars()
    )


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessage])
def get_conversation_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QueryLog]:
    """Return a conversation's turns, oldest first, to restore it as the active chat."""
    conversation = get_owned_conversation(db, conversation_id, current_user)
    return list(
        db.execute(
            select(QueryLog)
            .where(QueryLog.conversation_id == conversation.id)
            .order_by(QueryLog.created_at.asc())
        ).scalars()
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a conversation and its turns. Never touches the underlying knowledge-base documents."""
    conversation = get_owned_conversation(db, conversation_id, current_user)
    db.execute(QueryLog.__table__.delete().where(QueryLog.conversation_id == conversation.id))
    db.delete(conversation)
    db.commit()
