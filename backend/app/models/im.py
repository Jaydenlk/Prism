"""
Prism v2 — IM domain ORM models (DOC-01 v4 §4.2 — IM 域)

ImBinding:       maps a Prism user to an IM platform identity.
ImChannelConfig: global per-channel configuration (app_id, secrets, etc.).

v4 key change to ImBinding:
  Unique constraint changed from (channel, platform_user_id) to the
  three-tuple (channel, platform_user_id, platform_chat_id).
  Single-user DMs use platform_chat_id='' (empty string).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class ImBinding(Base):
    """
    im_bindings table — DOC-01 v4 §4.2

    Unique constraint (v4): (channel, platform_user_id, platform_chat_id)

    Single-user DMs: platform_chat_id = '' (empty string default).
    Group chats:     platform_chat_id = group/room ID.

    This allows one Prism user to be active in multiple group chats on the
    same IM platform simultaneously.
    """

    __tablename__ = "im_bindings"

    __table_args__ = (
        UniqueConstraint(
            "channel",
            "platform_user_id",
            "platform_chat_id",
            name="uq_im_bindings_channel_user_chat",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    platform_chat_id: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pairing_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    paired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="im_bindings")


class ImChannelConfig(Base, TimestampMixin):
    """
    im_channel_configs table — DOC-01 v4 §4.2

    One row per IM channel (feishu / wecom / telegram).
    ``channel`` has a UNIQUE constraint so there is at most one config row
    per channel type.
    ``config`` JSONB stores channel-specific secrets (app_id, bot_token, …).
    """

    __tablename__ = "im_channel_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    channel: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
