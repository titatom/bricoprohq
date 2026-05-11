"""add_publishing_tables

Adds the ``publish_attempts`` audit table and three new columns on
``content_drafts`` (``post_id``, ``post_url``, ``published_at``) populated
once a draft has actually been published upstream.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-11 00:04:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_drafts",
        sa.Column("post_id", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "content_drafts",
        sa.Column("post_url", sa.String(length=1000), nullable=False, server_default=""),
    )
    op.add_column("content_drafts", sa.Column("published_at", sa.DateTime(), nullable=True))

    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("target_account", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("post_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("post_url", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["draft_id"], ["content_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_publish_attempts_draft_id"), "publish_attempts", ["draft_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_publish_attempts_draft_id"), table_name="publish_attempts")
    op.drop_table("publish_attempts")
    op.drop_column("content_drafts", "published_at")
    op.drop_column("content_drafts", "post_url")
    op.drop_column("content_drafts", "post_id")
