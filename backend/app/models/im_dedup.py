"""
Prism v2 — ImMessageDedup ORM model (DOC-01 v4 §4.2 — IM 幂等域, v4 新增)

Idempotency table for IM webhook messages.  The IM Gateway checks this
table before processing any incoming message; duplicate platform_message_ids
are silently ignored.

Unique constraint: (channel, platform_message_id)
Index: (received_at) — for periodic cleanup of records older than 7 days.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.session import Session


class ImMessageDedup(Base):
    """
    im_message_dedup table — DOC-01 v4 §4.2 (v4 新增)

    ``channel``:             IM channel identifier ('feishu' | 'wecom' | 'telegram').
    ``platform_message_id``: The platform-native message ID.
    ``session_id``:          If the message was routed to a Prism session,
                             this FK is set after processing.
    """

    __tablename__ = "im_message_dedup"

    __table_args__ = (
        UniqueConstraint(
            "channel",
            "platform_message_id",
            name="uq_im_message_dedup_channel_msg",
        ),
        Index("ix_im_message_dedup_received_at", "received_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=True,
    )

    # Relationship
    session: Mapped["Session | None"] = relationship("Session")
