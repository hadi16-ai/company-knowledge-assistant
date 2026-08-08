"""Add page_count to documents

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-07

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("documents", "page_count")
