"""
Prism v2 — GoogleOAuthService (Task B: Google OAuth)

Handles:
  - Build Google consent / authorize URL (state CSRF via Redis)
  - Exchange authorization code for tokens via AsyncOAuth2Client
  - Verify id_token via Google tokeninfo endpoint
  - State stored as JSON: {"next": <front_url>}, TTL 600 s

Redis key schema:
  oauth:state:{state}  SETEX 600 s  →  json {"next": "<url>"}

References:
  - spec §2.5, §2.7, §3.3
  - authlib.integrations.httpx_client.AsyncOAuth2Client
  - https://accounts.google.com/.well-known/openid-configuration
"""
from __future__ import annotations

import json
import secrets
import urllib.parse
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

_STATE_TTL = 600  # seconds (10 minutes)
_STATE_KEY_PREFIX = "oauth:state:"


class GoogleOAuthService:
    """Google OAuth 2.0 + OIDC integration using authlib AsyncOAuth2Client."""

    def __init__(self, settings: Any, redis_client: Any) -> None:
        """
        Args:
            settings: App Settings instance (must have GOOGLE_OAUTH_CLIENT_ID,
                      GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI,
                      FRONTEND_BASE_URL).
            redis_client: Async redis client (may be None when only is_configured()
                          is called, e.g. from /auth/providers).
        """
        self._settings = settings
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Return True only if both client_id and client_secret are set."""
        client_id = getattr(self._settings, "GOOGLE_OAUTH_CLIENT_ID", "") or ""
        client_secret = getattr(self._settings, "GOOGLE_OAUTH_CLIENT_SECRET", "") or ""
        return bool(client_id.strip() and client_secret.strip())

    async def build_authorize_url(self, next_url: str = "") -> tuple[str, str]:
        """Construct Google consent URL and store state in Redis.

        Returns:
            (authorize_url, state)  — caller redirects to authorize_url.
        """
        state = secrets.token_urlsafe(32)
        state_key = f"{_STATE_KEY_PREFIX}{state}"
        state_value = json.dumps({"next": next_url})
        await self._redis.setex(state_key, _STATE_TTL, state_value)

        params = {
            "client_id": self._settings.GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": self._settings.GOOGLE_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        authorize_url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

        logger.info("google_oauth.authorize_url_built", state_prefix=state[:8])
        return authorize_url, state

    async def consume_state(self, state: str) -> Optional[dict]:
        """GETDEL the state key from Redis and return its payload, or None if missing.

        Consuming the state atomically (GETDEL) prevents CSRF replay.
        """
        state_key = f"{_STATE_KEY_PREFIX}{state}"
        raw = await self._redis.getdel(state_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens and verify id_token.

        Returns a dict with keys:
            google_id, email, email_verified (bool), name, picture

        Raises:
            ValueError: if token exchange or id_token verification fails.
        """
        from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore

        async with AsyncOAuth2Client(
            client_id=self._settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=self._settings.GOOGLE_OAUTH_CLIENT_SECRET,
            redirect_uri=self._settings.GOOGLE_OAUTH_REDIRECT_URI,
        ) as client:
            try:
                token_response = await client.fetch_token(
                    _GOOGLE_TOKEN_URL,
                    code=code,
                )
            except Exception as exc:
                logger.warning("google_oauth.token_exchange_failed", error=str(exc))
                raise ValueError(f"Google token exchange failed: {exc}") from exc

        id_token = token_response.get("id_token")
        if not id_token:
            raise ValueError("Google token response missing id_token")

        # Verify id_token via Google tokeninfo endpoint (server-side sig check)
        google_info = await self._verify_id_token(id_token)
        return google_info

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _verify_id_token(self, id_token: str) -> dict:
        """Verify id_token with Google tokeninfo endpoint and extract claims.

        Raises:
            ValueError: if token is invalid or email not present.
        """
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(
                _GOOGLE_TOKENINFO_URL,
                params={"id_token": id_token},
            )

        if resp.status_code != 200:
            logger.warning(
                "google_oauth.tokeninfo_failed",
                status_code=resp.status_code,
                body=resp.text[:200],
            )
            raise ValueError("Google id_token verification failed")

        claims: dict = resp.json()

        # Validate audience
        aud = claims.get("aud", "")
        if aud != self._settings.GOOGLE_OAUTH_CLIENT_ID:
            raise ValueError("id_token audience mismatch — token not intended for this app")

        sub = claims.get("sub")
        email = claims.get("email")
        if not sub or not email:
            raise ValueError("id_token missing required claims (sub/email)")

        email_verified_raw = claims.get("email_verified", "false")
        # Google returns "true"/"false" strings in tokeninfo
        email_verified = email_verified_raw is True or email_verified_raw == "true"

        result = {
            "google_id": sub,
            "email": email,
            "email_verified": email_verified,
            "name": claims.get("name", ""),
            "picture": claims.get("picture", ""),
        }

        logger.info(
            "google_oauth.id_token_verified",
            google_id_prefix=sub[:8],
            email_domain=email.split("@")[-1] if "@" in email else "?",
            email_verified=email_verified,
        )
        return result
