"""
Prism v2 — AuthChallengeService

Unified one-time token management for:
  - Email magic-link login   (type=magic_link_email)
  - Email OTP login          (type=otp_email)
  - Password reset           (type=password_reset_email)
  - SMS OTP (future)         (type=otp_sms)

Redis key format (spec §2.2):
  auth:challenge:{type}:{challenge_id}

challenge_id = uuid4 (stable key suffix)
token        = secrets.token_urlsafe(32) stored inside JSON value — compared on verify.
               For OTP challenges, `code` field holds the 6-digit number; `token` is None.

TTL = 900 seconds (15 minutes).

OTP challenge keying:
  The OTP verify endpoint receives {email, code} without a challenge_id.
  We key by identifier instead: auth:challenge:otp_email:{email}
  but still store challenge_id inside JSON for audit purposes.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()

CHALLENGE_TTL = 900  # 15 minutes

CHALLENGE_TYPES = {
    "magic_link_email",
    "otp_email",
    "password_reset_email",
    "otp_sms",
}


def _challenge_key(challenge_type: str, challenge_id: str) -> str:
    """Canonical Redis key for a challenge by ID."""
    return f"auth:challenge:{challenge_type}:{challenge_id}"


def _otp_key(challenge_type: str, identifier: str) -> str:
    """For OTP challenges keyed by identifier (e.g. email)."""
    return f"auth:challenge:{challenge_type}:{identifier}"


class AuthChallengeService:
    """Create, retrieve, and consume one-time auth challenge tokens."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_challenge(
        self,
        *,
        challenge_type: str,
        identifier: str,
        user_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """Create a magic-link or password-reset challenge (not OTP).

        Returns:
            {"challenge_id": str, "token": str}  — to be embedded in URL / log

        Redis key: auth:challenge:{type}:{challenge_id}
        Token stored inside JSON value, compared on verify.
        """
        if challenge_type not in CHALLENGE_TYPES:
            raise ValueError(f"Unknown challenge_type: {challenge_type}")

        challenge_id = str(uuid4())
        token = secrets.token_urlsafe(32)

        payload = {
            "challenge_id": challenge_id,
            "identifier": identifier,
            "user_id": user_id,
            "token": token,
            "code": None,
            "extra": extra or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        key = _challenge_key(challenge_type, challenge_id)
        await self._redis.setex(key, CHALLENGE_TTL, json.dumps(payload))

        logger.info(
            "auth.challenge.created",
            challenge_type=challenge_type,
            challenge_id=challenge_id,
            identifier=identifier,
        )

        return {"challenge_id": challenge_id, "token": token}

    async def create_otp_challenge(
        self,
        *,
        challenge_type: str,
        identifier: str,
        user_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """Create an OTP challenge keyed by identifier.

        Returns:
            {"challenge_id": str, "code": str}  — code is 6-digit string

        Redis key: auth:challenge:{type}:{identifier}
        Allows verify-by-{identifier, code} without a separate challenge_id param.
        """
        if challenge_type not in CHALLENGE_TYPES:
            raise ValueError(f"Unknown challenge_type: {challenge_type}")

        challenge_id = str(uuid4())
        code = str(secrets.randbelow(1_000_000)).zfill(6)

        payload = {
            "challenge_id": challenge_id,
            "identifier": identifier,
            "user_id": user_id,
            "token": None,
            "code": code,
            "extra": extra or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        key = _otp_key(challenge_type, identifier)
        await self._redis.setex(key, CHALLENGE_TTL, json.dumps(payload))

        logger.info(
            "auth.otp.created",
            challenge_type=challenge_type,
            challenge_id=challenge_id,
            identifier=identifier,
        )

        return {"challenge_id": challenge_id, "code": code}

    # ------------------------------------------------------------------
    # Verify (magic link / password reset)
    # ------------------------------------------------------------------

    async def verify_challenge(
        self,
        *,
        challenge_type: str,
        challenge_id: str,
        token: str,
    ) -> dict:
        """Verify a magic-link or password-reset challenge.

        Consumes the challenge atomically (DEL after GET).

        Returns:
            The stored payload dict on success.

        Raises:
            ValueError: if token invalid / expired / already used.
        """
        key = _challenge_key(challenge_type, challenge_id)
        raw = await self._redis.get(key)

        if raw is None:
            raise ValueError("Challenge not found or already used")

        payload: dict = json.loads(raw)

        if payload.get("token") != token:
            raise ValueError("Invalid challenge token")

        # Consume — atomic DEL (one-time use)
        await self._redis.delete(key)

        logger.info(
            "auth.challenge.verified",
            challenge_type=challenge_type,
            challenge_id=challenge_id,
            identifier=payload.get("identifier"),
        )

        return payload

    # ------------------------------------------------------------------
    # Verify OTP (by identifier + code)
    # ------------------------------------------------------------------

    async def verify_otp(
        self,
        *,
        challenge_type: str,
        identifier: str,
        code: str,
    ) -> dict:
        """Verify an OTP challenge by identifier + code.

        Consumes the challenge atomically.

        Returns:
            The stored payload dict on success.

        Raises:
            ValueError: if code invalid / expired / already used.
        """
        key = _otp_key(challenge_type, identifier)
        raw = await self._redis.get(key)

        if raw is None:
            raise ValueError("OTP not found or already used")

        payload: dict = json.loads(raw)

        if payload.get("code") != code:
            raise ValueError("Invalid OTP code")

        # Consume
        await self._redis.delete(key)

        logger.info(
            "auth.otp.verified",
            challenge_type=challenge_type,
            challenge_id=payload.get("challenge_id"),
            identifier=identifier,
        )

        return payload
