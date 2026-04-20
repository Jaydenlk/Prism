"""Session 4b — Discord send_card unit tests with mocked httpx (ADR-088 I5)."""
from __future__ import annotations

import pytest

from app.services.im_adapter import IMCardAction, IMOutgoingCard
from app.services.im_discord import DiscordAdapter


def _adapter(bot_token: str = "Bot-t") -> DiscordAdapter:
    return DiscordAdapter(
        config={
            "public_key": "00" * 32,
            "app_id": "1",
            "bot_token": bot_token,
        },
    )


def _card() -> IMOutgoingCard:
    return IMOutgoingCard(
        channel="discord",
        platform_chat_id="CHANNEL_ID",
        title="Test",
        body_markdown="body",
        actions=[IMCardAction(label="OK", action_id="ok", style="primary")],
    )


class _Resp:
    def __init__(self, status_code: int = 200, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {}


class _Client:
    def __init__(self, resp: _Resp, captured: dict) -> None:
        self._resp = resp
        self._captured = captured

    def __call__(self, timeout=None, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def post(self, url: str, **kwargs):
        self._captured["url"] = url
        self._captured["kwargs"] = kwargs
        return self._resp


@pytest.mark.asyncio
async def test_discord_send_card_builds_embed_and_components(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp(200), captured)
    monkeypatch.setattr("app.services.im_discord.httpx.AsyncClient", client)

    ok = await _adapter().send_card(_card())
    assert ok is True
    body = captured["kwargs"]["json"]
    assert body["embeds"][0]["title"] == "Test"
    assert body["components"][0]["type"] == 1  # ActionRow
    assert body["components"][0]["components"][0]["type"] == 2  # Button
    assert body["components"][0]["components"][0]["label"] == "OK"


@pytest.mark.asyncio
async def test_discord_send_card_no_bot_token_returns_false() -> None:
    assert await _adapter(bot_token="").send_card(_card()) is False


@pytest.mark.asyncio
async def test_discord_send_card_api_error_returns_false(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp(400, text="bad"), captured)
    monkeypatch.setattr("app.services.im_discord.httpx.AsyncClient", client)
    assert await _adapter().send_card(_card()) is False
