import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def _make_engine():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://bricopro:bricopro@db:5432/bricoprohq")
    return create_engine(url, future=True)


# Module-level singletons — re-assigned on reload via _reinit()
engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _reinit():
    """Re-read DATABASE_URL and rebuild engine/session. Called by tests after reloading."""
    global engine, SessionLocal
    engine = _make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
