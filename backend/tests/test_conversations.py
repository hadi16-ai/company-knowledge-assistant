"""Unit tests for the pure conversation-ownership predicate and title generation
(no DB — the full ownership *enforcement*, including cross-org/cross-user 404s,
is verified live against the running stack; see the slice's E2E pass)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.api.v1.conversations import _conversation_is_owned_by, generate_conversation_title
from app.db.models import Conversation


def _conversation(org_id: uuid.UUID, user_id: uuid.UUID) -> Conversation:
    return Conversation(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=user_id,
        title=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_conversation_owned_by_matching_org_and_user():
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    conversation = _conversation(org_id, user_id)
    assert _conversation_is_owned_by(conversation, org_id, user_id)


def test_conversation_not_owned_by_different_user_same_org():
    org_id, user_id, other_user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conversation = _conversation(org_id, user_id)
    assert not _conversation_is_owned_by(conversation, org_id, other_user_id)


def test_conversation_not_owned_by_different_org_same_user():
    org_id, other_org_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conversation = _conversation(org_id, user_id)
    assert not _conversation_is_owned_by(conversation, other_org_id, user_id)


def test_conversation_not_owned_when_both_org_and_user_differ():
    conversation = _conversation(uuid.uuid4(), uuid.uuid4())
    assert not _conversation_is_owned_by(conversation, uuid.uuid4(), uuid.uuid4())


def test_generate_title_short_question_unchanged():
    assert generate_conversation_title("What is the leave policy?") == "What is the leave policy?"


def test_generate_title_collapses_internal_whitespace():
    assert generate_conversation_title("What   is\n\nthe leave policy?") == "What is the leave policy?"


def test_generate_title_truncates_long_question_at_word_boundary():
    question = "What is the exact process for requesting reimbursement for business travel expenses incurred abroad?"
    title = generate_conversation_title(question, max_length=40)
    assert len(title) <= 41  # 40 + the ellipsis character
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")


def test_generate_title_falls_back_to_hard_truncation_when_first_word_exceeds_max_length():
    title = generate_conversation_title("Supercalifragilisticexpialidocious is one long word", max_length=15)
    assert title == "Supercalifragil…"
