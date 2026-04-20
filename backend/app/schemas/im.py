"""
Prism v2 — IM 相关 Pydantic Schemas (DOC-08 Task 8.1)

覆盖：
  - IM 渠道配置 (IMChannelConfigResponse / IMChannelConfigUpdate)
  - IM 绑定 (IMBindingResponse / PairingCodeResponse)
  - IM Webhook 内部结构（轻量）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# IM Channel Config
# ---------------------------------------------------------------------------

class IMChannelConfigResponse(BaseModel):
    """GET /im/channels 中单个渠道的响应体。

    id / created_at / updated_at 对"已知但未配置"的占位渠道可为空(DB 尚无行时)。
    """

    id: str
    channel: str
    is_enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class IMChannelConfigUpdate(BaseModel):
    """PATCH /im/channels/{channel} 请求体（admin only）。"""

    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# IM Binding
# ---------------------------------------------------------------------------

class IMBindingResponse(BaseModel):
    """单个 IM 绑定记录的响应体。"""

    id: str
    user_id: str
    channel: str
    platform_user_id: str
    platform_chat_id: str
    display_name: str | None
    paired_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PairingCodeResponse(BaseModel):
    """POST /im/bindings/pair 响应体。"""

    pairing_code: str = Field(description="6 位数字配对码")
    channel: str
    expires_at: datetime = Field(description="配对码过期时间（UTC）")


# ---------------------------------------------------------------------------
# Test-send (ADR-088 Session 4b)
# ---------------------------------------------------------------------------

class TestSendRequest(BaseModel):
    """POST /im/channels/{channel}/test-send body (admin-only).

    target_chat_id 为平台原生 id(feishu oc_xxxx / slack C0xxx / discord channel_id)。
    title 和 body 可选,默认为中文测试文案。
    """

    target_chat_id: str = Field(min_length=1, description="目标会话/群聊 ID")
    title: str | None = Field(default=None, description="卡片标题,缺省 'Prism 测试卡片'")
    body: str | None = Field(default=None, description="卡片正文 markdown,缺省标准测试文案")


# ---------------------------------------------------------------------------
# Webhook event (lightweight internal)
# ---------------------------------------------------------------------------

class IMWebhookEvent(BaseModel):
    """
    IM Webhook 事件封装（内部用，不暴露给前端）。

    用于 Webhook 端点 → IMGateway 之间的数据传递。
    """

    channel: str
    platform_user_id: str
    platform_chat_id: str
    text: str
    msg_id: str
    raw: dict[str, Any] = Field(default_factory=dict)
