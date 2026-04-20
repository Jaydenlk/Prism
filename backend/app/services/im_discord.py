"""
Prism v2 — Discord IM adapter (DOC-IM2 I3, ADR-088).

Mode: HTTP Interactions (webhook-style).  Discord signs every interaction
payload with Ed25519.  Invalid signatures must receive a non-2xx (we choose
401) since Discord actively probes bad signatures during app validation.

Signature per https://discord.com/developers/docs/interactions/receiving-and-responding:
  sig = Ed25519(application_public_key, timestamp + body)
  — headers: X-Signature-Ed25519 (hex), X-Signature-Timestamp (UTC str).

PING interaction (type=1) must be answered with PONG (type=1).

Send message via POST https://discord.com/api/v10/channels/{channel_id}/messages
with Bot {DISCORD_BOT_TOKEN}.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

logger = structlog.get_logger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_MAX_LENGTH = 2000  # Discord per-message char limit


class DiscordAdapter(IMAdapter):
    """Discord HTTP-interactions adapter.

    Configuration resolution: settings > config dict fallback.
      config = {
        "public_key": "<hex-64>",
        "app_id": "...",
        "bot_token": "...",
      }
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        settings: Any = None,
    ) -> None:
        super().__init__()
        cfg = config or {}
        if settings is not None and getattr(settings, "DISCORD_PUBLIC_KEY", ""):
            self._public_key_hex: str = settings.DISCORD_PUBLIC_KEY
            self._app_id: str = settings.DISCORD_APP_ID
            self._bot_token: str = settings.DISCORD_BOT_TOKEN
        else:
            self._public_key_hex = cfg.get("public_key", "")
            self._app_id = cfg.get("app_id", "")
            self._bot_token = cfg.get("bot_token", "")
        self._running = False

    @property
    def channel_name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        # A configured adapter needs at least the public key to verify sigs.
        # bot_token is optional for receive-only setups (ack + outbound via webhook).
        return bool(self._public_key_hex)

    async def start(self) -> None:
        if not self.is_configured():
            logger.warning("discord.adapter.start_skipped", reason="public_key not configured")
            return
        self._running = True
        logger.info("discord.adapter.started")

    async def stop(self) -> None:
        self._running = False
        logger.info("discord.adapter.stopped")

    # ------------------------------------------------------------------
    # Signature verification (Ed25519)
    # ------------------------------------------------------------------

    def verify_signature(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify X-Signature-Ed25519 against timestamp+body using PyNaCl.

        Fail-closed on:
          - missing headers
          - missing/invalid public_key
          - malformed hex signature (wrong length, non-hex)
          - cryptographic verify failure
        """
        sig_hex = headers.get("X-Signature-Ed25519", "")
        ts = headers.get("X-Signature-Timestamp", "")
        if not sig_hex or not ts or not self._public_key_hex:
            return False

        try:
            from nacl.signing import VerifyKey
            from nacl.exceptions import BadSignatureError
        except ImportError:
            logger.error("discord.verify_signature.pynacl_missing")
            return False

        try:
            verify_key = VerifyKey(bytes.fromhex(self._public_key_hex))
            sig_bytes = bytes.fromhex(sig_hex)
            verify_key.verify(ts.encode("ascii") + body, sig_bytes)
            return True
        except BadSignatureError:
            return False
        except (ValueError, TypeError) as exc:
            logger.warning("discord.verify_signature.malformed", error=str(exc))
            return False

    @staticmethod
    def build_ping_response(parsed_body: dict[str, Any]) -> dict[str, int] | None:
        """Return Discord PONG (type:1) if body is a PING, else None.

        Per Discord docs, PING's response is literally {"type": 1}.
        """
        if parsed_body.get("type") == 1:
            return {"type": 1}
        return None

    # ------------------------------------------------------------------
    # Event parsing
    # ------------------------------------------------------------------

    async def parse_event(self, body: bytes) -> IMIncomingMessage | None:
        """Parse a Discord interaction body into a normalized IMIncomingMessage.

        PING (type=1) is NOT returned here — caller should handle it first via
        build_ping_response(). APPLICATION_COMMAND (type=2) with user text
        content is mapped to a normal message.
        """
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        if parsed.get("type") != 2:
            return None  # non-command interactions not handled here

        data = parsed.get("data", {})
        user_id = (parsed.get("member", {}).get("user") or parsed.get("user") or {}).get("id", "")
        channel_id = parsed.get("channel_id", "")
        msg_id = parsed.get("id", "")

        # Extract first text option; if none, fall back to the command name
        options = data.get("options", []) or []
        text = ""
        for opt in options:
            if opt.get("type") == 3:  # STRING option
                text = str(opt.get("value", "")).strip()
                break
        if not text:
            text = data.get("name", "").strip()

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

    # ------------------------------------------------------------------
    # Outgoing
    # ------------------------------------------------------------------

    async def send(self, message: IMOutgoingMessage) -> bool:
        if not self._bot_token:
            logger.warning("discord.send.no_bot_token", chat_id=message.platform_chat_id)
            return False

        text = message.text[:DISCORD_MAX_LENGTH]
        payload: dict[str, Any] = {"content": text}
        if message.reply_to_message_id:
            payload["message_reference"] = {"message_id": message.reply_to_message_id}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{DISCORD_API_BASE}/channels/{message.platform_chat_id}/messages",
                    headers={
                        "Authorization": f"Bot {self._bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code >= 300:
                logger.error(
                    "discord.send.api_error",
                    chat_id=message.platform_chat_id,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
                return False
            logger.info("discord.send.success", chat_id=message.platform_chat_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("discord.send.exception", chat_id=message.platform_chat_id, error=str(exc))
            return False
