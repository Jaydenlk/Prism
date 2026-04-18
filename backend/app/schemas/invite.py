"""
Prism v2 — Invite Code Schemas (DOC-06 Task 6.2)

Request / response models for invite-code management endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateInviteCodeRequest(BaseModel):
    """POST /admin/invite-codes — create a new invite code."""

    max_uses: int = 1
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_max_uses(self) -> "CreateInviteCodeRequest":
        if self.max_uses < 1:
            raise ValueError("max_uses must be at least 1")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class InviteCodeResponse(BaseModel):
    """Returned by invite-code CRUD endpoints."""

    id: str
    code: str                     # PRISM-XXXXXXXX format, shown to admin
    created_by: str               # creator user_id
    max_uses: int
    used_count: int
    expires_at: Optional[datetime]
    is_valid: bool                # computed: not expired AND used_count < max_uses
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, invite: object) -> "InviteCodeResponse":
        """Build response from InviteCode ORM model, computing is_valid."""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        not_expired = (
            invite.expires_at is None  # type: ignore[attr-defined]
            or invite.expires_at > now  # type: ignore[attr-defined]
        )
        not_exhausted = (
            invite.used_count < invite.max_uses  # type: ignore[attr-defined]
        )
        return cls(
            id=str(invite.id),  # type: ignore[attr-defined]
            code=invite.code,  # type: ignore[attr-defined]
            created_by=str(invite.created_by),  # type: ignore[attr-defined]
            max_uses=invite.max_uses,  # type: ignore[attr-defined]
            used_count=invite.used_count,  # type: ignore[attr-defined]
            expires_at=invite.expires_at,  # type: ignore[attr-defined]
            is_valid=not_expired and not_exhausted,
            created_at=invite.created_at,  # type: ignore[attr-defined]
        )
