"""
Prism v2 — McpServer & UserMcpInstall ORM models (DOC-01 v4 §4.2 — MCP 域)

mcp_servers: global registry of MCP servers (system or user-defined).
user_mcp_installs: per-user enablement + config override.

Unique constraint on user_mcp_installs: (user_id, mcp_server_id)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class McpServer(Base):
    """
    mcp_servers table — DOC-01 v4 §4.2

    ``scope`` = 'system' (built-in) | 'user' (user-defined).
    ``command`` + ``args`` define how to launch the MCP server process.
    ``env`` holds environment variables passed to the child process.
    """

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="system"
    )
    command: Mapped[str] = mapped_column(String(500), nullable=False)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    env: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    user_installs: Mapped[list["UserMcpInstall"]] = relationship(
        "UserMcpInstall",
        back_populates="mcp_server",
        cascade="all, delete-orphan",
    )


class UserMcpInstall(Base):
    """
    user_mcp_installs table — DOC-01 v4 §4.2

    Links a User to an McpServer, with per-user enable/disable toggle and
    optional config overrides.

    Unique constraint: (user_id, mcp_server_id)
    """

    __tablename__ = "user_mcp_installs"

    __table_args__ = (
        UniqueConstraint("user_id", "mcp_server_id", name="uq_user_mcp_installs"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mcp_server_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_override: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="mcp_installs")
    mcp_server: Mapped["McpServer"] = relationship(
        "McpServer", back_populates="user_installs"
    )
