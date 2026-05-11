"""add_integration_upstream_version

Adds an ``upstream_version`` column to ``integrations``. Populated
opportunistically by each connector's ``ping()`` so the dashboard can show
"Immich 1.118.2 — last error 4 min ago" instead of just "error".

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-11 00:03:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column("upstream_version", sa.String(length=100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("integrations", "upstream_version")
