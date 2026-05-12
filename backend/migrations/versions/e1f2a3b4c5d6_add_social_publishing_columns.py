"""add_social_publishing_columns

Add platform_post_id, platform_account_id, published_at, publish_error to
content_drafts and create post_metric_snapshots for time-series KPI data.

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-05-12 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("content_drafts") as batch_op:
        batch_op.add_column(sa.Column("platform_post_id", sa.String(512), nullable=True))
        batch_op.add_column(sa.Column("platform_account_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("publish_error", sa.Text(), nullable=True))

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["draft_id"], ["content_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_metric_snapshots_draft_id", "post_metric_snapshots", ["draft_id"])


def downgrade() -> None:
    op.drop_index("ix_post_metric_snapshots_draft_id", table_name="post_metric_snapshots")
    op.drop_table("post_metric_snapshots")

    with op.batch_alter_table("content_drafts") as batch_op:
        batch_op.drop_column("publish_error")
        batch_op.drop_column("published_at")
        batch_op.drop_column("platform_account_id")
        batch_op.drop_column("platform_post_id")
