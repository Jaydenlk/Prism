"""
Prism v2 — Run ORM model (DOC-01 v4 §4.2 — 执行域)

Includes all Harness-related fields added in v4:
  turn_count, harness_summary, cache_hit_tokens, cache_miss_tokens,
  cache_creation_tokens, agent_type, run_mode, parent_run_id,
  harness_version, subprocess_pid
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.message import Message
    from app.models.tool_execution import ToolExecution
    from app.models.coordinator_plan import CoordinatorPlan
    from app.models.permission_request import PermissionRequest


class Run(Base, TimestampMixin):
    """
    runs table — DOC-01 v4 §4.2 (执行域)

    One Run = one TAOR execution lifecycle.  A session may have many Runs
    (conversation turns → new run each time).

    Indexes (per DOC-01 v4):
      - (session_id, created_at DESC)
      - (user_id, created_at DESC)
      - (status) WHERE status = 'pending'
    """

    __tablename__ = "runs"

    __table_args__ = (
        Index("ix_runs_session_created", "session_id", "created_at"),
        Index("ix_runs_user_created", "user_id", "created_at"),
        Index(
            "ix_runs_status_pending",
            "status",
            postgresql_where="status = 'pending'",
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
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("providers.id"),
        nullable=True,
    )
    schedule_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="immediate"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Token accounting --------------------------------------------------
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # v4 Harness cache fields
    cache_hit_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_miss_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    # --- Execution stats ---------------------------------------------------
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Run mode (v4 Harness) --------------------------------------------
    run_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="foreground"
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("runs.id"),
        nullable=True,
    )

    # --- Harness metadata (v4) -------------------------------------------
    harness_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    harness_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # --- Subprocess info (v4 DOC-07 Task 7.2 — cancel 三模式) -----------
    # PID of the CLI executor subprocess; None before launch or after exit.
    subprocess_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Timing -----------------------------------------------------------
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="runs",
        foreign_keys=[session_id],
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    provider: Mapped["Provider | None"] = relationship(
        "Provider", foreign_keys=[provider_id]
    )
    parent_run: Mapped["Run | None"] = relationship(
        "Run",
        remote_side="Run.id",
        foreign_keys=[parent_run_id],
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="run", cascade="all, delete-orphan"
    )
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution", back_populates="run", cascade="all, delete-orphan"
    )
    coordinator_plans: Mapped[list["CoordinatorPlan"]] = relationship(
        "CoordinatorPlan", back_populates="run", cascade="all, delete-orphan"
    )
    permission_requests: Mapped[list["PermissionRequest"]] = relationship(
        "PermissionRequest", back_populates="run", cascade="all, delete-orphan"
    )
