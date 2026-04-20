"""Session 4b — Slack send_card unit tests with mocked httpx (ADR-088 I5)."""
from __future__ import annotations

import pytest

from app.services.im_adapter import IMCardAction, IMOutgoingCard
from app.services.im_slack import SlackAdapter


def _adapter() -> SlackAdapter:
    return SlackAdapter(
        config={
            "signing_secret": "s" * 32,
            "bot_token": "xoxb-test",
            "mode": "events",
        },
    )


def _card() -> IMOutgoingCard:
    return IMOutgoingCard(
        channel="slack",
        platform_chat_id="C0TEST",
        title="Test",
        body_markdown="*bold* note",
        actions=[IMCardAction(label="OK", action_id="ok", style="primary")],
    )


class _Resp:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict:
        return self._data


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
async def test_slack_send_card_builds_blocks(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp({"ok": True}), captured)
    monkeypatch.setattr("app.services.im_slack.httpx.AsyncClient", client)

    ok = await _adapter().send_card(_card())
    assert ok is True
    body = captured["kwargs"]["json"]
    assert body["channel"] == "C0TEST"
    kinds = [b["type"] for b in body["blocks"]]
    assert "header" in kinds and "section" in kinds and "actions" in kinds


@pytest.mark.asyncio
async def test_slack_send_card_not_configured_returns_false() -> None:
    a = SlackAdapter(config={"signing_secret": "", "bot_token": ""})
    assert await a.send_card(_card()) is False


@pytest.mark.asyncio
async def test_slack_send_card_api_error_returns_false(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp({"ok": False, "error": "channel_not_found"}), captured)
    monkeypatch.setattr("app.services.im_slack.httpx.AsyncClient", client)
    assert await _adapter().send_card(_card()) is False
