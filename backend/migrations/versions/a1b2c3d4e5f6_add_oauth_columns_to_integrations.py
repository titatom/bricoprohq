"""add_oauth_columns_to_integrations

Revision ID: a1b2c3d4e5f6
Revises: 9c8e1a2b3d4f
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9c8e1a2b3d4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('integrations', sa.Column('oauth_access_token', sa.Text(), nullable=True))
    op.add_column('integrations', sa.Column('oauth_refresh_token', sa.Text(), nullable=True))
    op.add_column('integrations', sa.Column('oauth_token_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('integrations', 'oauth_token_expires_at')
    op.drop_column('integrations', 'oauth_refresh_token')
    op.drop_column('integrations', 'oauth_access_token')
