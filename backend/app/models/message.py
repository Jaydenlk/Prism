"""
Prism v2 — Message ORM model (DOC-01 v4 §4.2 — 执行域)

Stores PrismMessage-format content as JSONB.
v4 new fields: sequence_no, text_preview, is_skill_context, skill_name.

Indexes:
  - (session_id, sequence_no)
  - (run_id)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.run import Run


class Message(Base):
    """
    messages table — DOC-01 v4 §4.2

    ``sequence_no`` is a per-session globally ordered integer.
    Per ADR-060, concurrent callers MUST NOT use max+1; use a PostgreSQL
    advisory lock or per-session sequence (DOC-07 Task 7.2).

    ``is_skill_context`` marks messages injected by a Skill's Level-2
    context injection.  Compaction engine preserves these preferentially
    (ADR-017 / DOC-01 v4 §5).
    """

    __tablename__ = "messages"

    __table_args__ = (
        Index("ix_messages_session_seq", "session_id", "sequence_no"),
        Index("ix_messages_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    text_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # v4 Skill context fields (ADR-017)
    is_skill_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    skill_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")
    run: Mapped["Run | None"] = relationship("Run", back_populates="messages")
