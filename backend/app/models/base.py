"""
Prism v2 — SQLAlchemy Declarative Base + Mixins (ADR-001, ADR-002)

All ORM models inherit from Base.  Tables with standard timestamps also mix
in TimestampMixin.

UUIDv7 is used as the primary key type (time-ordered, globally unique).
"""
from __future__ import annotations

from datetime import datetime

from uuid_extensions import uuid7
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all Prism ORM models."""


class TimestampMixin:
    """
    Adds ``created_at`` and ``updated_at`` columns to any table.

    Both columns are TIMESTAMPTZ (timezone=True) and default to the
    current server time.  ``updated_at`` is automatically refreshed on
    every UPDATE via the ``onupdate`` hook.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def generate_uuid() -> str:
    """Return a new UUIDv7 string (ADR-002)."""
    return str(uuid7())
