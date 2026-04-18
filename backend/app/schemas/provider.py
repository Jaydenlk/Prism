"""
Prism v2 — Provider Pydantic Schemas (DOC-02 Task 2.3)

ADR-010: scope 二值 ('system' | 'user')
ADR-011: config.capabilities 强制字段,缺失 422
ADR-012: api_key 响应中永远返回掩码版本

Exports:
  ProviderCapabilitiesSchema  — Pydantic 版本的 ProviderCapabilities dataclass
  ProviderPreset              — 内置预设模型(带 capabilities)
  CreateProviderRequest       — 创建请求(config.capabilities 必填)
  UpdateProviderRequest       — 更新请求(所有字段可选)
  ProviderResponse            — 响应(含 api_key_masked,不含明文)
  TestProviderResponse        — 连通性探测响应
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Capabilities schema (Pydantic 版本,对应 executor/adapters/base.py ProviderCapabilities)
# ---------------------------------------------------------------------------

class ProviderCapabilitiesSchema(BaseModel):
    """Provider 能力声明 — Pydantic 版 (ADR-011)

    每个 Provider 必须声明其能力集,ProviderManager 用于构建 Driver 实例。
    """
    prompt_cache: bool = False        # 支持 Anthropic Prompt Cache
    streaming_tools: bool = True      # 支持流式返回工具调用参数
    extended_thinking: bool = False   # 支持 thinking 过程可见
    vision: bool = False              # 支持图片输入


# ---------------------------------------------------------------------------
# Internal helper: API Key mask
# ---------------------------------------------------------------------------

def _mask_key(api_key: str) -> str:
    """Mask an API key for safe display.

    Rules:
      - Length < 8: return '***'
      - Otherwise: first 3 chars + '...' + last 4 chars
    """
    if len(api_key) < 8:
        return "***"
    return api_key[:3] + "..." + api_key[-4:]


# ---------------------------------------------------------------------------
# Provider preset (used by GET /providers/presets — no auth required)
# ---------------------------------------------------------------------------

class ProviderPreset(BaseModel):
    """内置 Provider 预设 (ADR-011: 每个预设必须带 capabilities 声明)"""
    name: str                              # "Anthropic Claude"
    protocol: Literal["anthropic", "openai"]  # 协议类型
    base_url: str                          # Provider API base URL
    model_id: str                          # 默认推荐模型 ID
    description: str                       # 简短说明
    capabilities: ProviderCapabilitiesSchema  # v4 强制,预设必须声明能力


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateProviderRequest(BaseModel):
    """创建 Provider 请求 — config.capabilities 缺失时返回 422 (ADR-011)"""

    name: str
    protocol: Literal["anthropic", "openai"]
    base_url: str
    api_key: str
    model_id: str
    is_default: bool = False
    priority: int = 0
    config: dict = {}

    @field_validator("config")
    @classmethod
    def capabilities_required(cls, v: dict) -> dict:
        """ADR-011: config.capabilities 是强制字段,缺失则触发 422."""
        if "capabilities" not in v:
            raise ValueError(
                "config.capabilities is required. "
                "Provide at least {} (all defaults to false/true) or use "
                "POST /providers/{id}/test to auto-detect."
            )
        return v


class UpdateProviderRequest(BaseModel):
    """更新 Provider 请求 — 所有字段均可选,仅传需要修改的字段"""

    name: Optional[str] = None
    api_key: Optional[str] = None       # 仅在需要更新 API Key 时传入
    is_default: Optional[bool] = None
    priority: Optional[int] = None
    config: Optional[dict] = None       # 如传入 config,同样需要包含 capabilities


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ProviderResponse(BaseModel):
    """Provider 响应体 — api_key 永远返回掩码版本 (ADR-012)"""

    id: str
    scope: str                          # 'system' | 'user'
    name: str
    protocol: str
    base_url: str
    api_key_masked: str                 # "sk-...a1b2" — 永不返回明文
    model_id: str
    is_default: bool
    priority: int
    is_healthy: bool
    config: dict                        # 含 capabilities 子对象
    user_id: Optional[str] = None      # scope='system' 时为 None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestProviderResponse(BaseModel):
    """连通性探测响应 (ADR-011: 返回 detected_capabilities)"""

    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    detected_capabilities: Optional[ProviderCapabilitiesSchema] = None
