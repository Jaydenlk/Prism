"""
Prism v2 — CoordinatorPlan ORM model (DOC-01 v4 §4.2 — 执行恢复域, v4 新增)

Checkpoints the Coordinator Agent's plan so execution can resume after a
subprocess crash.

Indexes:
  - (run_id)
  - (status, updated_at DESC)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.run import Run


class CoordinatorPlan(Base):
    """
    coordinator_plans table — DOC-01 v4 §4.2 (v4 新增)

    ``plan_json`` stores the full multi-step plan.
    ``current_step_index`` advances as each step completes.
    ``step_results`` accumulates completed step outputs.
    After a subprocess restart, the coordinator reads this row to resume
    from ``current_step_index``.
    """

    __tablename__ = "coordinator_plans"

    __table_args__ = (
        Index("ix_coordinator_plans_run_id", "run_id"),
        Index("ix_coordinator_plans_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_step_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    step_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    run: Mapped["Run"] = relationship("Run", back_populates="coordinator_plans")
