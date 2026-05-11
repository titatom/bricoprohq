"""encrypt_integration_secrets

Re-write every existing `integrations` row through the application's
`EncryptedText` type so that legacy plaintext credentials and OAuth tokens
are upgraded to ciphertext at rest. The column types do not change here —
the schema is already `Text` — but the values are touched once so the
``enc:v1:`` prefix is applied.

The migration is safe to re-run because the crypto helpers are idempotent
(already-encrypted values are passed through unchanged).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-11 00:01:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, config_json, oauth_access_token, oauth_refresh_token "
            "FROM integrations"
        )
    ).fetchall()

    if not rows:
        return

    # Lazy import: the migration runs against a live application install where
    # `app.services.crypto` is on the Python path.
    from app.services.crypto import encrypt, is_encrypted

    for row_id, config_json, access_token, refresh_token in rows:
        updates: dict[str, str | None] = {}
        if config_json is not None and not is_encrypted(config_json):
            updates["config_json"] = encrypt(config_json)
        if access_token is not None and not is_encrypted(access_token):
            updates["oauth_access_token"] = encrypt(access_token)
        if refresh_token is not None and not is_encrypted(refresh_token):
            updates["oauth_refresh_token"] = encrypt(refresh_token)
        if not updates:
            continue
        assignments = ", ".join(f"{column} = :{column}" for column in updates)
        bind.execute(
            sa.text(f"UPDATE integrations SET {assignments} WHERE id = :id"),
            {**updates, "id": row_id},
        )


def downgrade() -> None:
    """Decrypt back to plaintext. Only useful before disabling at-rest encryption."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, config_json, oauth_access_token, oauth_refresh_token "
            "FROM integrations"
        )
    ).fetchall()

    if not rows:
        return

    from app.services.crypto import decrypt, is_encrypted

    for row_id, config_json, access_token, refresh_token in rows:
        updates: dict[str, str | None] = {}
        if config_json is not None and is_encrypted(config_json):
            updates["config_json"] = decrypt(config_json)
        if access_token is not None and is_encrypted(access_token):
            updates["oauth_access_token"] = decrypt(access_token)
        if refresh_token is not None and is_encrypted(refresh_token):
            updates["oauth_refresh_token"] = decrypt(refresh_token)
        if not updates:
            continue
        assignments = ", ".join(f"{column} = :{column}" for column in updates)
        bind.execute(
            sa.text(f"UPDATE integrations SET {assignments} WHERE id = :id"),
            {**updates, "id": row_id},
        )
