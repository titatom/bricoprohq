"""
Symmetric encryption helpers for at-rest secrets (integration credentials,
OAuth tokens). Built on `cryptography.fernet`, with a Fernet key derived from
the application's `SECRET_KEY` via HKDF-SHA256.

All ciphertexts are stored with the `enc:v1:` prefix so the decrypt helper can
distinguish encrypted columns from legacy plaintext rows that pre-date this
module. Plaintext input is passed through unchanged on read and re-encrypted
on the next write — no migration is required for existing rows, but a
backfill pass is still useful so the database does not retain plaintext
copies of old values.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..secret_key import current_secret_key

ENCRYPTED_PREFIX = "enc:v1:"
_HKDF_SALT = b"bricoprohq.secret-encryption.v1"
_HKDF_INFO = b"bricoprohq.fernet-key.v1"


def _derive_fernet_key(secret_key: str) -> bytes:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    ).derive(secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def _fernet() -> Fernet:
    return Fernet(_derive_fernet_key(current_secret_key()))


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt(value: str | None) -> str | None:
    """Encrypt a plaintext string; idempotent if already encrypted."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if is_encrypted(value):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt(value: str | None) -> str | None:
    """Decrypt a value if it carries the `enc:v1:` prefix; otherwise return as-is."""
    if value is None:
        return None
    if not is_encrypted(value):
        return value
    token = value[len(ENCRYPTED_PREFIX):].encode("ascii")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise InvalidToken(
            "Could not decrypt stored secret. This usually means SECRET_KEY changed "
            "since the value was written. Restore the previous SECRET_KEY or re-enter "
            "the affected credentials in Settings."
        ) from exc
