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
    """GET /im/channels 中单个渠道的响应体。"""

    id: str
    channel: str
    is_enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

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
