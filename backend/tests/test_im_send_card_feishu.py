"""Session 4b — Feishu send_card unit tests with mocked httpx (ADR-088 I5)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services.im_adapter import IMCardAction, IMOutgoingCard
from app.services.im_feishu import FeishuAdapter


def _adapter() -> FeishuAdapter:
    return FeishuAdapter(
        config={
            "app_id": "cli_x",
            "app_secret": "s",
            "encrypt_key": "e",
            "verify_token": "v",
        },
    )


def _card() -> IMOutgoingCard:
    return IMOutgoingCard(
        channel="feishu",
        platform_chat_id="oc_test",
        title="测试",
        body_markdown="**bold** body",
        actions=[IMCardAction(label="确认", action_id="ok")],
    )


class _Resp:
    def __init__(self, data: dict) -> None:
        self._data = data

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
async def test_feishu_send_card_builds_interactive_payload(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp({"code": 0, "msg": "ok"}), captured)
    monkeypatch.setattr("app.services.im_feishu.httpx.AsyncClient", client)
    a = _adapter()
    monkeypatch.setattr(a, "_ensure_token", AsyncMock(return_value="tkn"))

    ok = await a.send_card(_card())
    assert ok is True
    body = captured["kwargs"].get("json") or {}
    assert body.get("msg_type") == "interactive"
    assert body.get("receive_id") == "oc_test"
    content = json.loads(body.get("content") or "{}")
    assert content["header"]["title"]["content"] == "测试"
    elements = content["elements"]
    assert any(el.get("tag") == "div" for el in elements)
    assert any(el.get("tag") == "action" for el in elements)


@pytest.mark.asyncio
async def test_feishu_send_card_not_configured_returns_false() -> None:
    a = FeishuAdapter(config={"app_id": "", "app_secret": ""})
    assert await a.send_card(_card()) is False


@pytest.mark.asyncio
async def test_feishu_send_card_api_error_returns_false(monkeypatch) -> None:
    captured: dict = {}
    client = _Client(_Resp({"code": 99, "msg": "bad"}), captured)
    monkeypatch.setattr("app.services.im_feishu.httpx.AsyncClient", client)
    a = _adapter()
    monkeypatch.setattr(a, "_ensure_token", AsyncMock(return_value="tkn"))
    assert await a.send_card(_card()) is False
