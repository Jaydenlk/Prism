"""
Prism v2 — PluginLibrary ORM model (Task A-3)

User-owned plugin library. Each row represents a plugin saved by the user
(from the conversational builder or manually imported).

Unique constraint: (user_id, name)
Index: (user_id, created_at DESC)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class PluginLibrary(Base):
    """
    plugins_library table — Task A-3 (migration 007)

    Stores user-owned plugin manifests produced by the plugin_builder agent
    or manually saved. ``manifest_yaml`` holds the raw YAML string.
    ``manifest_json`` caches the parsed representation.
    """

    __tablename__ = "plugins_library"

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_plugins_library_user_name"),
        Index("ix_plugins_library_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manifest_yaml: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manifest_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    plugin_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="tool", server_default="tool"
    )
    permissions_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="plugin_library_entries")
