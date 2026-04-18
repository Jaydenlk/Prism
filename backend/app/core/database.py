"""
Prism v2 — SQLAlchemy Database Engine & Session (ADR-001)

Uses SQLAlchemy 2.0 *synchronous* mode.  Async is explicitly avoided to
eliminate the complexity around lazy-load / selectinload (ADR-001).

Exported symbols
----------------
engine       — shared Engine, created once at import time
SessionLocal — sessionmaker bound to engine
Base         — declarative base imported from models.base (re-exported here
               so other modules can do ``from app.core.database import Base``)
get_db       — FastAPI dependency that yields a Session and closes it in finally
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # reconnect on stale connections
    pool_size=5,
    max_overflow=10,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a database session, closing it after the request completes."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
