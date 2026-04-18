"""
Prism v2 — Provider ORM model (DOC-01 v4 §4.2 — 模型 & Provider 域)

v4 key changes:
  - scope field added ('system' | 'user')
  - user_id is nullable (NULL when scope='system')
  - CHECK constraint: (scope='system' AND user_id IS NULL) OR
                      (scope='user' AND user_id IS NOT NULL)
  - config JSONB must contain 'capabilities' sub-object (app-layer validation)

Indexes:
  - (scope, user_id, is_default)
  - (scope, user_id, priority)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class Provider(Base, TimestampMixin):
    """
    providers table — DOC-01 v4 §4.2

    ``scope`` = 'system' means a globally shared preset (no user_id).
    ``scope`` = 'user' means a user-owned private provider (user_id NOT NULL).

    CHECK constraint enforces this invariant at DB level.

    ``config`` JSONB stores extra settings including the mandatory
    ``capabilities`` object (validated at application layer, not DB level).
    """

    __tablename__ = "providers"

    __table_args__ = (
        CheckConstraint(
            "(scope = 'system' AND user_id IS NULL) OR "
            "(scope = 'user' AND user_id IS NOT NULL)",
            name="ck_providers_scope_user_id",
        ),
        Index("ix_providers_scope_user_default", "scope", "user_id", "is_default"),
        Index("ix_providers_scope_user_priority", "scope", "user_id", "priority"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationship (NULL for scope='system')
    user: Mapped["User | None"] = relationship("User", back_populates="providers")
