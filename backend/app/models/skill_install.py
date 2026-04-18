"""
Prism v2 — SkillInstall ORM model (DOC-01 v4 §4.2 — 插件 & Skill 域, v4 新增)

Tracks installed Skills per user.  Corresponds to the Skills Market API
(DOC-01 §6.12).

Unique constraint: (user_id, skill_name)
Index: (user_id, installed_at DESC)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class SkillInstall(Base):
    """
    skill_installs table — DOC-01 v4 §4.2 (v4 新增)

    ``skill_name`` includes the namespace, e.g. "community/obra/superpowers".
    ``source`` tracks where the skill came from.
    ``metadata`` caches SKILL.md frontmatter + aggregated multi-source info.
    """

    __tablename__ = "skill_installs"

    __table_args__ = (
        UniqueConstraint("user_id", "skill_name", name="uq_skill_installs_user_skill"),
        Index("ix_skill_installs_user_installed", "user_id", "installed_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="skill_installs")
