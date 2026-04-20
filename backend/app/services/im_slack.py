"""
Prism v2 — Slack IM adapter (DOC-IM2 I2, ADR-088).

Mode: Events API (HTTP) by default; Socket Mode opt-in via IM_SLACK_MODE=socket.

Signature verification per https://docs.slack.dev/authentication/verifying-requests-from-slack:
  base = "v0:{ts}:{body}"
  expected = "v0=" + hmac_sha256(signing_secret, base).hexdigest()
  Plus a ±5-minute timestamp window to prevent replay.

Send message via POST https://slack.com/api/chat.postMessage with Bearer xoxb-...
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

logger = structlog.get_logger(__name__)

SLACK_API_BASE = "https://slack.com/api"
SLACK_MAX_LENGTH = 3000
_TIMESTAMP_WINDOW_SECONDS = 300  # ±5 minutes (Slack's recommended replay window)


class SlackAdapter(IMAdapter):
    """Slack Events-API adapter (HTTP mode).

    Configuration resolution: settings > config dict fallback.
      config = {
        "signing_secret": "...",
        "bot_token": "xoxb-...",
        "app_token": "xapp-...",  # only if mode=socket
        "mode": "events",
      }
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        settings: Any = None,
    ) -> None:
        super().__init__()
        cfg = config or {}
        if settings is not None and getattr(settings, "SLACK_SIGNING_SECRET", ""):
            self._signing_secret: str = settings.SLACK_SIGNING_SECRET
            self._bot_token: str = settings.SLACK_BOT_TOKEN
            self._app_token: str = settings.SLACK_APP_TOKEN
            self._mode: str = settings.IM_SLACK_MODE or "events"
        else:
            self._signing_secret = cfg.get("signing_secret", "")
            self._bot_token = cfg.get("bot_token", "")
            self._app_token = cfg.get("app_token", "")
            self._mode = cfg.get("mode", "events")
        self._running = False

    @property
    def channel_name(self) -> str:
        return "slack"

    def is_configured(self) -> bool:
        return bool(self._signing_secret and self._bot_token)

    async def start(self) -> None:
        if not self.is_configured():
            logger.warning("slack.adapter.start_skipped", reason="signing_secret or bot_token not configured")
            return
        self._running = True
        logger.info("slack.adapter.started", mode=self._mode)

    async def stop(self) -> None:
        self._running = False
        logger.info("slack.adapter.stopped")

    # ------------------------------------------------------------------
    # Signature verification (Slack Events API contract)
    # ------------------------------------------------------------------

    def verify_signature(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify X-Slack-Signature against body using HMAC-SHA256 v0: prefix.

        Rejects if timestamp is outside a ±5-minute window (replay guard) or
        if signing_secret is not configured (fail-closed).
        """
        if not self._signing_secret:
            return False

        ts = headers.get("X-Slack-Request-Timestamp", "")
        sig = headers.get("X-Slack-Signature", "")
        if not ts or not sig:
            return False

        try:
            ts_int = int(ts)
        except ValueError:
            return False

        # Timestamp window check (replay attack guard)
        now = int(time.time())
        if abs(now - ts_int) > _TIMESTAMP_WINDOW_SECONDS:
            return False

        base = b"v0:" + ts.encode("ascii") + b":" + body
        expected = "v0=" + hmac.new(
            self._signing_secret.encode("utf-8"),
            base,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig)

    @staticmethod
    def build_url_verification_response(body: bytes) -> dict[str, str] | None:
        """Slack's one-time URL verification handshake.

        If the body is a url_verification event, return the required
        {"challenge": "..."} dict.  Returns None otherwise.
        """
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if parsed.get("type") == "url_verification":
            return {"challenge": parsed.get("challenge", "")}
        return None

    # ------------------------------------------------------------------
    # Event handling + outgoing message
    # ------------------------------------------------------------------

    async def parse_event(self, body: bytes) -> IMIncomingMessage | None:
        """Parse a Slack Events API body into a normalized IMIncomingMessage.

        Only `type:event_callback` with `event.type=message` and non-bot
        authors are converted; bot_id or subtype=bot_message events are
        filtered out to prevent self-loops.
        """
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if parsed.get("type") != "event_callback":
            return None
        event = parsed.get("event", {})
        if event.get("type") != "message":
            return None
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return None

        text = event.get("text", "").strip()
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        msg_id = event.get("ts", "")  # Slack uses ts as message identifier

        if not text or not user_id or not msg_id:
            return None

        return IMIncomingMessage(
            channel=self.channel_name,
            platform_user_id=user_id,
            platform_chat_id=channel_id or user_id,
            text=text,
            msg_id=msg_id,
            raw=parsed,
        )

    async def send(self, message: IMOutgoingMessage) -> bool:
        if not self.is_configured():
            logger.warning("slack.send.not_configured", chat_id=message.platform_chat_id)
            return False

        text = message.text[:SLACK_MAX_LENGTH]
        payload: dict[str, Any] = {
            "channel": message.platform_chat_id,
            "text": text,
        }
        if message.reply_to_message_id:
            payload["thread_ts"] = message.reply_to_message_id

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{SLACK_API_BASE}/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self._bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                )
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "slack.send.api_error",
                    chat_id=message.platform_chat_id,
                    error=data.get("error"),
                )
                return False
            logger.info("slack.send.success", chat_id=message.platform_chat_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("slack.send.exception", chat_id=message.platform_chat_id, error=str(exc))
            return False
