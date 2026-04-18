"""
Prism v2 — ToolExecution ORM model (DOC-01 v4 §4.2 — 执行域)

Records each tool invocation including Harness governance fields:
  permission_decision, hook_modified (v4 new fields).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.run import Run


class ToolExecution(Base):
    """
    tool_executions table — DOC-01 v4 §4.2

    ``permission_decision``: 'allow' | 'deny' | 'ask' — Harness decision.
    ``hook_modified``:       True if a Hook rewrote the tool input.
    """

    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # v4 Harness fields
    permission_decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    hook_modified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        "Session", back_populates="tool_executions"
    )
    run: Mapped["Run"] = relationship("Run", back_populates="tool_executions")
