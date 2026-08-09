"""Add conversations table, query_log.conversation_id, backfill legacy history

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_TITLE_MAX_LENGTH = 60


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_org_id", "conversations", ["org_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.add_column(
        "query_log",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
    )
    op.create_index("ix_query_log_conversation_id", "query_log", ["conversation_id"])

    _backfill_legacy_conversations()


def _backfill_legacy_conversations() -> None:
    """Wrap each user's pre-existing flat query_log history into one conversation.

    Without this, everything asked before this migration would silently
    disappear from the new conversation sidebar even though the query_log
    rows themselves are untouched — this keeps existing history visible and
    openable as a single "legacy" thread per (org, user) instead.
    """
    connection = op.get_bind()

    owners = connection.execute(
        sa.text("SELECT DISTINCT org_id, user_id FROM query_log WHERE conversation_id IS NULL")
    ).fetchall()

    for org_id, user_id in owners:
        first_query = connection.execute(
            sa.text(
                "SELECT query FROM query_log "
                "WHERE org_id = :org_id AND user_id = :user_id "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"org_id": org_id, "user_id": user_id},
        ).scalar()

        title = (first_query or "Previous conversation").strip()[:_LEGACY_TITLE_MAX_LENGTH]
        conversation_id = uuid.uuid4()

        connection.execute(
            sa.text(
                "INSERT INTO conversations (id, org_id, user_id, title, created_at, updated_at) "
                "VALUES (:id, :org_id, :user_id, :title, now(), now())"
            ),
            {"id": conversation_id, "org_id": org_id, "user_id": user_id, "title": title},
        )
        connection.execute(
            sa.text(
                "UPDATE query_log SET conversation_id = :conversation_id "
                "WHERE org_id = :org_id AND user_id = :user_id AND conversation_id IS NULL"
            ),
            {"conversation_id": conversation_id, "org_id": org_id, "user_id": user_id},
        )


def downgrade() -> None:
    op.drop_index("ix_query_log_conversation_id", table_name="query_log")
    op.drop_column("query_log", "conversation_id")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_org_id", table_name="conversations")
    op.drop_table("conversations")
