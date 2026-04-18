"""
Prism v2 — Invite Code Service (DOC-06 Task 6.2)

Invite-code business logic:
  - generate_code()  : generate "PRISM-XXXXXXXX" random code
  - create()         : create InviteCode row (dedup loop)
  - validate()       : check exists + not expired + not exhausted
  - consume()        : increment used_count
  - list_all()       : return all codes, newest first
  - revoke()         : set max_uses = used_count (makes is_valid = False)

Invite code format: "PRISM-" prefix + 8 uppercase alphanumeric chars,
e.g. "PRISM-A3B7C9D2".
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import InviteCode
from app.models.base import generate_uuid
from app.schemas.invite import CreateInviteCodeRequest


class InviteService:
    """Service layer for invite-code lifecycle management."""

    _ALPHABET = string.ascii_uppercase + string.digits
    _CODE_LENGTH = 8
    _PREFIX = "PRISM-"

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def generate_code(self) -> str:
        """Generate a random 8-char code with PRISM- prefix."""
        suffix = "".join(
            secrets.choice(self._ALPHABET) for _ in range(self._CODE_LENGTH)
        )
        return f"{self._PREFIX}{suffix}"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, created_by: str, data: CreateInviteCodeRequest) -> InviteCode:
        """Create a new invite code, retrying on the rare collision.

        Args:
            created_by: user_id of the admin generating the code
            data:       validated request body

        Returns:
            Flushed (not yet committed) InviteCode ORM row
        """
        code = self.generate_code()
        # Collision guard — extremely unlikely but required by spec
        while self._db.query(InviteCode).filter(InviteCode.code == code).first():
            code = self.generate_code()

        invite = InviteCode(
            id=generate_uuid(),
            code=code,
            created_by=created_by,
            max_uses=data.max_uses,
            expires_at=data.expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(invite)
        self._db.flush()
        return invite

    def validate(self, code: str) -> InviteCode:
        """Validate an invite code for use at registration time.

        Checks:
          1. Code exists in DB
          2. Not expired (expires_at is None or > now)
          3. Not exhausted (used_count < max_uses)

        Raises:
            HTTPException 400: any invalid condition
        """
        invite = (
            self._db.query(InviteCode)
            .filter(InviteCode.code == code)
            .first()
        )
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code",
            )

        now = datetime.now(timezone.utc)
        if invite.expires_at is not None and invite.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code has expired",
            )

        if invite.used_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code has reached its maximum usage limit",
            )

        return invite

    def consume(self, invite: InviteCode) -> None:
        """Increment the used_count by 1 (flush only, caller commits)."""
        invite.used_count += 1
        self._db.flush()

    def list_all(self) -> list[InviteCode]:
        """Return all invite codes, newest first."""
        return (
            self._db.query(InviteCode)
            .order_by(InviteCode.created_at.desc())
            .all()
        )

    def get_by_id(self, invite_id: str) -> InviteCode | None:
        """Fetch a single invite code by PK."""
        return self._db.query(InviteCode).filter(InviteCode.id == invite_id).first()

    def revoke(self, invite_id: str) -> InviteCode:
        """Revoke an invite code by setting max_uses = used_count.

        After revocation is_valid becomes False because used_count >= max_uses.

        Raises:
            HTTPException 404: code not found
        """
        invite = self.get_by_id(invite_id)
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite code not found",
            )
        invite.max_uses = invite.used_count
        self._db.flush()
        return invite
