"""
Prism v2 — Session & SessionQueueItem ORM models (DOC-01 v4 §4.2 — 会话域)
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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.run import Run
    from app.models.message import Message
    from app.models.tool_execution import ToolExecution


class Session(Base, TimestampMixin):
    """
    sessions table — DOC-01 v4 §4.2 (会话域)

    Represents a conversation context.  ``blocking_run_id`` points to the Run
    currently executing inside this session.

    Indexes (per DOC-01 v4):
      - (user_id, updated_at DESC)
      - (user_id, is_pinned, updated_at DESC)
    """

    __tablename__ = "sessions"

    __table_args__ = (
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_sessions_user_pinned_updated", "user_id", "is_pinned", "updated_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle"
    )
    # FK to runs.id — forward reference; NULL until a Run is executing.
    blocking_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    config_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    im_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    im_chat_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    blocking_run: Mapped["Run | None"] = relationship(
        "Run",
        foreign_keys=[blocking_run_id],
        primaryjoin="Session.blocking_run_id == Run.id",
        uselist=False,
    )
    runs: Mapped[list["Run"]] = relationship(
        "Run",
        back_populates="session",
        foreign_keys="Run.session_id",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution", back_populates="session", cascade="all, delete-orphan"
    )
    queue_items: Mapped[list["SessionQueueItem"]] = relationship(
        "SessionQueueItem",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SessionQueueItem(Base):
    """
    session_queue_items table — DOC-01 v4 §4.2 (会话域)

    Queued prompts waiting for a session to become idle.

    Index: (session_id, status, sequence_no)
    """

    __tablename__ = "session_queue_items"

    __table_args__ = (
        Index(
            "ix_session_queue_items_session_status_seq",
            "session_id",
            "status",
            "sequence_no",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued"
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship
    session: Mapped["Session"] = relationship(
        "Session", back_populates="queue_items"
    )
