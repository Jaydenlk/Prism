"""
Prism v2 — User & InviteCode ORM models (DOC-01 v4 §4.2 — 用户域)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Integer, JSON, text
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
    from app.models.plugin_library import PluginLibrary


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

    # Multi-channel auth fields (migration 006)
    phone: Mapped[Optional[str]] = mapped_column(
        String(20), unique=True, nullable=True, default=None
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, default=None
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
    plugin_library_entries: Mapped[list["PluginLibrary"]] = relationship(
        "PluginLibrary", back_populates="user", cascade="all, delete-orphan"
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
        ForeignKey("users.id", ondelete="SET NULL"),
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


class AuthConfig(Base):
    """
    auth_config table — multi-channel auth global switches (migration 006)

    Stores key/value pairs for auth configuration.
    PK is the key string (not UUID).  value_json is any JSON-serializable value.
    Bootstrap rows created in migration 006.
    """

    __tablename__ = "auth_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
