"""
Runtime resolver for the application's `SECRET_KEY`.

Resolution order, in priority:

1. The `SECRET_KEY` env var, when set to a non-empty value other than the
   placeholder `"change-me"`. This is the only path used in production.
2. A persisted dev key stored at `$DATA_DIR/secret_key`. Auto-generated on
   first call if missing. This keeps a developer / single-node Docker setup
   working without forcing operators to pre-generate a key, while still
   producing a stable value across restarts so JWTs and encrypted columns
   remain valid.

When `APP_ENV=production` and the env var is missing or set to the
placeholder, `resolve_secret_key()` raises `RuntimeError`. This refuses to
start the app with a known-default secret in production, instead of silently
falling back to a stored value an operator may not be aware of.

Callers should re-resolve via `current_secret_key()` rather than caching a
module-level constant: tests reload `app.main` between scenarios with
different env vars, and the `auth` and `crypto` modules need to follow.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

log = logging.getLogger("bricopro.secret_key")

DEFAULT_PLACEHOLDER = "change-me"
DEV_KEY_FILENAME = "secret_key"
MIN_KEY_LENGTH = 16

# In-process fallback when DATA_DIR is not writable. Stable for the lifetime
# of the Python interpreter, so JWTs and Fernet ciphertext stay valid across
# requests inside the same worker even when no on-disk key can be persisted.
_ephemeral_dev_key: str | None = None


class SecretKeyMisconfigured(RuntimeError):
    """Raised when SECRET_KEY is missing/default in a production environment."""


def _is_production() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "/data"))


def _read_or_create_dev_key() -> str:
    global _ephemeral_dev_key

    data_dir = _data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if _ephemeral_dev_key is None:
            log.warning(
                "Could not create DATA_DIR %s for secret_key fallback (%s); "
                "generating an in-memory key for this process. Set SECRET_KEY explicitly "
                "to keep encrypted data and JWTs valid across restarts.",
                data_dir,
                exc,
            )
            _ephemeral_dev_key = secrets.token_hex(32)
        return _ephemeral_dev_key

    path = data_dir / DEV_KEY_FILENAME
    if path.exists():
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError as exc:
            log.warning("Could not read existing dev secret_key at %s: %s", path, exc)

    value = secrets.token_hex(32)
    try:
        path.write_text(value, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        log.warning(
            "SECRET_KEY env var not set; generated a development key and stored it at %s. "
            "Set SECRET_KEY explicitly before deploying to production.",
            path,
        )
        return value
    except OSError as exc:
        if _ephemeral_dev_key is None:
            log.warning(
                "Could not persist dev secret_key at %s (%s); using an in-memory key for this process.",
                path,
                exc,
            )
            _ephemeral_dev_key = value
        return _ephemeral_dev_key


def resolve_secret_key() -> str:
    """Return the SECRET_KEY to use for JWT and encryption, applying fallbacks."""
    env_value = (os.getenv("SECRET_KEY") or "").strip()
    if env_value and env_value != DEFAULT_PLACEHOLDER:
        if len(env_value) < MIN_KEY_LENGTH:
            log.warning(
                "SECRET_KEY is shorter than %d characters; generate a stronger value with "
                "`python3 -c \"import secrets; print(secrets.token_hex(32))\"`.",
                MIN_KEY_LENGTH,
            )
        return env_value

    if _is_production():
        raise SecretKeyMisconfigured(
            "SECRET_KEY is missing or set to the default placeholder while APP_ENV=production. "
            "Generate one with `python3 -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and set it via the SECRET_KEY environment variable."
        )

    return _read_or_create_dev_key()


def current_secret_key() -> str:
    """Convenience accessor used by other modules; never caches across calls."""
    return resolve_secret_key()
