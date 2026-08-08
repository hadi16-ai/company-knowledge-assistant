"""Extend user_role to 5 tiers, add users.expires_at, add invitations table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres can't add enum values inside the same transaction that might
    # reference them, and Alembic wraps migrations in a transaction by
    # default — run these in an autocommit block to sidestep that entirely.
    # Existing "admin"/"employee" rows and already-issued JWTs are unaffected;
    # this only adds new values.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'manager'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'guest'")

    op.add_column("users", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    user_role = postgresql.ENUM(
        "super_admin", "admin", "manager", "employee", "guest", name="user_role", create_type=False
    )

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email_hint", sa.String(length=255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index("ix_invitations_org_id", "invitations", ["org_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_org_id", table_name="invitations")
    op.drop_table("invitations")
    op.drop_column("users", "expires_at")
    # Postgres cannot drop individual enum values (no ALTER TYPE ... DROP
    # VALUE), so "super_admin"/"manager"/"guest" remain valid user_role
    # members after downgrade. This is a known, accepted limitation — not a
    # silent no-op — of adding enum values in Postgres.
