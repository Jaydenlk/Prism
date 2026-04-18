"""
Prism v2 — User & InviteCode ORM models (DOC-01 v4 §4.2 — 用户域)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.provider import Provider
    from app.models.mcp_server import UserMcpInstall
    from app.models.im import ImBinding
    from app.models.audit import AuditLog
    from app.models.skill_install import SkillInstall
    from app.models.user_memory import UserMemory


class User(Base, TimestampMixin):
    """
    users table — DOC-01 v4 §4.2 (用户域)

    Primary authentication entity.  ``role`` is either 'admin' or 'user'.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # DOC-09 Task 9.3: soft-disable flag (ADR-083)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships (back-populated in child models)
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    providers: Mapped[list["Provider"]] = relationship(
        "Provider", back_populates="user", cascade="all, delete-orphan"
    )
    mcp_installs: Mapped[list["UserMcpInstall"]] = relationship(
        "UserMcpInstall", back_populates="user", cascade="all, delete-orphan"
    )
    im_bindings: Mapped[list["ImBinding"]] = relationship(
        "ImBinding", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user"
    )
    skill_installs: Mapped[list["SkillInstall"]] = relationship(
        "SkillInstall", back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["UserMemory"]] = relationship(
        "UserMemory", back_populates="user", cascade="all, delete-orphan"
    )
    invite_codes: Mapped[list["InviteCode"]] = relationship(
        "InviteCode", back_populates="created_by_user"
    )


class InviteCode(Base):
    """
    invite_codes table — DOC-01 v4 §4.2 (用户域)

    Invite-only registration flow.  ``expires_at`` is NULL for never-expiring
    codes.  ``used_count`` is incremented each time the code is consumed.
    """

    __tablename__ = "invite_codes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(36),
        # No ON DELETE CASCADE — keep invite_codes even if creator is deleted
        nullable=False,
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship
    created_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="invite_codes",
        foreign_keys=[created_by],
    )
