"""
Prism v2 — AuthConfigService

Read/write auth_config table rows.

Keys (bootstrapped in migration 006):
  allow_oauth_signup_without_invite  bool — Google OAuth without invite code
  allow_phone_registration           bool — Phone+password registration
  require_email_verification         bool — Require email verification before login

All values are stored as JSON in value_json column.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.models.user import AuthConfig

logger = structlog.get_logger()

# Bootstrap defaults (mirrors migration 006)
DEFAULTS: dict[str, Any] = {
    "allow_oauth_signup_without_invite": False,
    "allow_phone_registration": True,
    "require_email_verification": False,
}


class AuthConfigService:
    """Manage auth_config table entries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self) -> list[AuthConfig]:
        """Return all auth_config rows ordered by key."""
        return self._db.query(AuthConfig).order_by(AuthConfig.key).all()

    def get(self, key: str) -> Any:
        """Return the parsed value for a key, or the default if key not found."""
        row = self._db.query(AuthConfig).filter(AuthConfig.key == key).first()
        if row is None:
            return DEFAULTS.get(key)
        return row.value_json

    def set(
        self,
        key: str,
        value: Any,
        *,
        updated_by: Optional[str] = None,
    ) -> AuthConfig:
        """Upsert an auth_config entry.

        Returns the updated AuthConfig row.
        """
        row = self._db.query(AuthConfig).filter(AuthConfig.key == key).first()
        if row is None:
            row = AuthConfig(key=key, value_json=value)
            self._db.add(row)
        else:
            row.value_json = value

        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = updated_by
        self._db.flush()

        logger.info(
            "auth_config.updated",
            key=key,
            value=value,
            updated_by=updated_by,
        )

        return row

    def is_phone_registration_allowed(self) -> bool:
        """Convenience accessor for phone registration toggle."""
        return bool(self.get("allow_phone_registration"))

    def is_oauth_signup_without_invite(self) -> bool:
        """Convenience accessor for OAuth without invite gate."""
        return bool(self.get("allow_oauth_signup_without_invite"))
