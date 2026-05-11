"""add_image_ids_planned_time_to_drafts

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-11 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("content_drafts", sa.Column("image_ids", sa.Text(), nullable=False, server_default=""))
    op.add_column("content_drafts", sa.Column("planned_time", sa.String(length=10), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("content_drafts", "planned_time")
    op.drop_column("content_drafts", "image_ids")
