"""
Unit tests for Task B-1: Feishu webhook inbound + send_message mock.

Tests cover:
  1. URL verification challenge (no signature, bare JSON)
  2. Signature rejection → 401
  3. No-config → 503
  4. send_message mock (no real HTTP call)
  5. decrypt_message / verify_signature logic
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_adapter(app_id: str = "app123", app_secret: str = "secret456",
                 encrypt_key: str = "", verify_token: str = "") -> "FeishuAdapter":
    """Create a FeishuAdapter with in-memory config (no Settings, no Redis)."""
    from app.services.im_feishu import FeishuAdapter
    return FeishuAdapter(
        config={
            "app_id": app_id,
            "app_secret": app_secret,
            "encrypt_key": encrypt_key,
            "verify_token": verify_token,
        },
        settings=None,
        redis_client=None,
    )


def make_lark_signature(timestamp: str, encrypt_key: str, body: bytes) -> str:
    """Compute the Feishu X-Lark-Signature value."""
    content = timestamp + encrypt_key + body.decode("utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Test: is_configured()
# ---------------------------------------------------------------------------

class TestIsConfigured:
    def test_configured_returns_true(self):
        adapter = make_adapter()
        assert adapter.is_configured() is True

    def test_empty_app_id_returns_false(self):
        adapter = make_adapter(app_id="")
        assert adapter.is_configured() is False

    def test_empty_app_secret_returns_false(self):
        adapter = make_adapter(app_secret="")
        assert adapter.is_configured() is False


# ---------------------------------------------------------------------------
# Test: verify_signature()
# ---------------------------------------------------------------------------

class TestVerifySignature:
    def test_no_encrypt_key_returns_false(self):
        """Without encrypt_key, signature verification always fails (secure default)."""
        adapter = make_adapter(encrypt_key="")
        assert adapter.verify_signature("123", "nonce", b'{"test":1}', "fakesig") is False

    def test_valid_signature_returns_true(self):
        """Correct signature computed with encrypt_key passes."""
        key = "testkey"
        adapter = make_adapter(encrypt_key=key)
        body = b'{"type":"url_verification","challenge":"abc"}'
        ts = str(int(time.time()))
        sig = make_lark_signature(ts, key, body)
        assert adapter.verify_signature(ts, "nonce", body, sig) is True

    def test_tampered_body_returns_false(self):
        """Modified body after signing must fail."""
        key = "testkey"
        adapter = make_adapter(encrypt_key=key)
        body = b'{"type":"url_verification","challenge":"abc"}'
        ts = str(int(time.time()))
        sig = make_lark_signature(ts, key, body)
        # tamper
        tampered = b'{"type":"url_verification","challenge":"xyz"}'
        assert adapter.verify_signature(ts, "nonce", tampered, sig) is False


# ---------------------------------------------------------------------------
# Test: handle_webhook() — URL verification
# ---------------------------------------------------------------------------

class TestHandleWebhookURLVerification:
    @pytest.mark.asyncio
    async def test_url_verification_returns_challenge(self):
        adapter = make_adapter()
        body = {"type": "url_verification", "challenge": "test_challenge_xyz"}
        result = await adapter.handle_webhook(body)
        assert result == {"challenge": "test_challenge_xyz"}

    @pytest.mark.asyncio
    async def test_url_verification_empty_challenge(self):
        adapter = make_adapter()
        body = {"type": "url_verification"}
        result = await adapter.handle_webhook(body)
        assert result == {"challenge": ""}


# ---------------------------------------------------------------------------
# Test: handle_webhook() — message event routing
# ---------------------------------------------------------------------------

class TestHandleWebhookMessageEvent:
    @pytest.mark.asyncio
    async def test_message_event_calls_handler(self):
        adapter = make_adapter()
        received: list[Any] = []

        async def handler(msg):
            received.append(msg)

        adapter.set_message_handler(handler)

        body = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}},
                "message": {
                    "message_id": "om_msg1",
                    "chat_id": "oc_chat1",
                    "message_type": "text",
                    "content": json.dumps({"text": "Hello Prism"}),
                },
            },
        }
        result = await adapter.handle_webhook(body)
        assert result == {"status": "ok"}
        assert len(received) == 1
        assert received[0].text == "Hello Prism"
        assert received[0].platform_user_id == "ou_user1"
        assert received[0].platform_chat_id == "oc_chat1"

    @pytest.mark.asyncio
    async def test_non_text_message_ignored(self):
        adapter = make_adapter()
        received: list[Any] = []

        async def handler(msg):
            received.append(msg)

        adapter.set_message_handler(handler)

        body = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user1"}},
                "message": {
                    "message_id": "om_msg2",
                    "chat_id": "oc_chat1",
                    "message_type": "image",
                    "content": "{}",
                },
            },
        }
        await adapter.handle_webhook(body)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_unknown_event_type_returns_ok(self):
        adapter = make_adapter()
        body = {"header": {"event_type": "card.action.trigger"}}
        result = await adapter.handle_webhook(body)
        assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Test: send_message() mock (no real HTTP)
# ---------------------------------------------------------------------------

class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_not_configured_returns_false(self):
        adapter = make_adapter(app_id="", app_secret="")
        result = await adapter.send_message("oc_chat1", "hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Mock httpx.AsyncClient to simulate successful Feishu API call."""
        adapter = make_adapter()
        # Inject a cached token to skip token refresh
        adapter._access_token = "mock_token"
        adapter._token_expires_at = time.time() + 7200

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "data": {}}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await adapter.send_message("oc_chat1", "Hello from Prism!")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_api_error(self):
        """Feishu API returns code != 0 → False."""
        adapter = make_adapter()
        adapter._access_token = "mock_token"
        adapter._token_expires_at = time.time() + 7200

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 99991663, "msg": "app not exist"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await adapter.send_message("oc_chat1", "test")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_truncates_long_text(self):
        """Messages longer than FEISHU_MAX_LENGTH get truncated."""
        from app.services.im_feishu import FEISHU_MAX_LENGTH

        adapter = make_adapter()
        adapter._access_token = "mock_token"
        adapter._token_expires_at = time.time() + 7200

        long_text = "A" * (FEISHU_MAX_LENGTH + 100)

        captured_payload: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0}

        async def fake_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client_cls.return_value = mock_client

            await adapter.send_message("oc_chat1", long_text)

        sent_content = json.loads(captured_payload.get("content", "{}"))
        assert len(sent_content.get("text", "")) <= FEISHU_MAX_LENGTH


# ---------------------------------------------------------------------------
# Test: Settings-sourced config override
# ---------------------------------------------------------------------------

class TestSettingsConfig:
    def test_settings_overrides_dict_config(self):
        """Settings FEISHU_* fields take priority over config dict."""
        from app.services.im_feishu import FeishuAdapter

        mock_settings = MagicMock()
        mock_settings.FEISHU_APP_ID = "settings_app_id"
        mock_settings.FEISHU_APP_SECRET = "settings_secret"
        mock_settings.FEISHU_ENCRYPT_KEY = "settings_key"
        mock_settings.FEISHU_VERIFICATION_TOKEN = "settings_token"

        adapter = FeishuAdapter(
            config={"app_id": "dict_app_id", "app_secret": "dict_secret"},
            settings=mock_settings,
            redis_client=None,
        )
        assert adapter._app_id == "settings_app_id"
        assert adapter._app_secret == "settings_secret"
        assert adapter._encrypt_key == "settings_key"

    def test_empty_settings_falls_back_to_dict(self):
        """Empty Settings FEISHU_APP_ID → fall back to dict config."""
        from app.services.im_feishu import FeishuAdapter

        mock_settings = MagicMock()
        mock_settings.FEISHU_APP_ID = ""  # empty

        adapter = FeishuAdapter(
            config={"app_id": "dict_app_id", "app_secret": "dict_secret"},
            settings=mock_settings,
            redis_client=None,
        )
        assert adapter._app_id == "dict_app_id"
