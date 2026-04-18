"""
Prism v2 — AuditLog ORM model (DOC-01 v4 §4.2 — 审计域)

``action`` uses dot-namespaced strings.  Harness events use the prefix
``harness.*`` (e.g. harness.guardrail_trigger, harness.hook_fire).

Indexes:
  - (user_id, created_at DESC)
  - (action, created_at DESC)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """
    audit_logs table — DOC-01 v4 §4.2

    Harness action naming convention (v4):
      harness.guardrail_trigger
      harness.hook_fire
      harness.permission_deny
      harness.permission_ask
      harness.circuit_break
      harness.loop_detected
      harness.compaction_trigger
      harness.entropy_alert

    ``resource_id`` is stored as VARCHAR(36) to hold UUIDs without requiring
    a proper FK (resource_type is polymorphic).
    """

    __tablename__ = "audit_logs"

    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship (nullable — system events have no user)
    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
