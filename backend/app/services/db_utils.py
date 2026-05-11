"""
Small utilities shared by route handlers when committing changes to the
database. Centralizes the "rollback + map to a friendly HTTP error" pattern
so endpoints don't all reinvent it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

log = logging.getLogger("bricopro.db_utils")


@contextmanager
def commit_or_400(db: Session, *, conflict_message: str = "Conflict — value already exists."):
    """
    Yield to the caller, then commit. On `IntegrityError` rollback and raise
    HTTP 409. On any other exception rollback and re-raise.

    Usage::

        with commit_or_400(db):
            db.add(thing)
    """
    try:
        yield
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        log.info("IntegrityError: %s", exc.orig if hasattr(exc, "orig") else exc)
        raise HTTPException(409, conflict_message) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def is_masked_secret(value: str | None) -> bool:
    """Return True if a string is the bullet-mask placeholder used by the UI."""
    if not value:
        return False
    return all(c == "•" for c in value)
