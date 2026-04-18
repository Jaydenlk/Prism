"""
Prism v2 — UserMemory ORM model (DOC-01 v4 §4.2 — Memory 域, v4 新增)

Stores per-user memory text (Layer 2 of the 6-layer Memory architecture).
There is exactly one row per user (unique constraint on user_id).
History is tracked via ``version`` + audit_logs.

Unique constraint: (user_id) — one row per user.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class UserMemory(Base):
    """
    user_memories table — DOC-01 v4 §4.2 (v4 新增)

    ``memory_text``:  Free-form user preference / session summary text.
    ``version``:      Incremented on each update.
    ``updated_by``:   'auto' (SessionEnd Hook) | 'manual' (user).
    """

    __tablename__ = "user_memories"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_memories_user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="memories")
