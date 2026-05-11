"""add_integration_last_error

Adds ``last_error`` and ``last_error_at`` columns to ``integrations`` so the
dashboard can show the most recent failure for an integration without having
to read the cache payload or the server logs.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-11 00:02:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("integrations", sa.Column("last_error_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("integrations", "last_error_at")
    op.drop_column("integrations", "last_error")
