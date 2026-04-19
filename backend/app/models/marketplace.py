"""
Prism v2 — MarketplaceRegistry ORM model (DOC-SK R1, ADR-086)

Registers external Claude Code-format plugin marketplaces. Each row holds the
registered URL, display name, and a cached copy of the marketplace's
`.claude-plugin/marketplace.json` catalog (shape per
https://code.claude.com/docs/en/plugin-marketplaces):

    {name, owner: {name, email?}, plugins: [...], metadata?}

Plugins installed from a marketplace link back via skill_installs.marketplace_id
(FK, ON DELETE SET NULL).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User


class MarketplaceRegistry(Base):
    __tablename__ = "marketplace_registry"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    catalog_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
