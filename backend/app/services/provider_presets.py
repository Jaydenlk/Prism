"""
Prism v2 — 内置 Provider 预设清单 (DOC-02 Task 2.3, ADR-011)

按 DOC-00 v4 §9.2 的 8 家厂商给出预设。每个预设必须带 capabilities 声明。
Bootstrap 时由 ProviderService.bootstrap_presets() 幂等注册为 scope='system' 记录。

厂商列表(8 家):
  1. Anthropic 官方
  2. OpenAI 官方
  3. MiniMax
  4. DeepSeek
  5. Kimi (Moonshot AI)
  6. Qwen (通义千问 / Alibaba Cloud)
  7. 智谱 AI (GLM)
  8. Google Gemini (OpenAI-compatible)
"""
from __future__ import annotations

try:
    from app.schemas.provider import ProviderCapabilitiesSchema, ProviderPreset
except ImportError:
    # Allow import when running tests from repo root with backend/ on sys.path
    from backend.app.schemas.provider import ProviderCapabilitiesSchema, ProviderPreset  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# 内置预设清单 (ADR-011: 每个 ProviderPreset 必须含 capabilities)
# ---------------------------------------------------------------------------

BUILTIN_PRESETS: list[ProviderPreset] = [
    # 1. Anthropic 官方 — 完整 capabilities(含 prompt_cache + extended_thinking + vision)
    ProviderPreset(
        name="Anthropic Claude",
        protocol="anthropic",
        base_url="https://api.anthropic.com",
        model_id="claude-sonnet-4-6",
        description="Anthropic 官方 API — 支持 Prompt Cache / 流式工具 / extended_thinking / 视觉",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=True,
            streaming_tools=True,
            extended_thinking=True,
            vision=True,
        ),
    ),
    # 2. OpenAI 官方 — GPT-4o,支持视觉和流式工具,不支持 prompt_cache
    ProviderPreset(
        name="OpenAI GPT",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        model_id="gpt-4o",
        description="OpenAI 官方 API — 支持视觉 / 流式工具,不支持 Prompt Cache",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=True,
        ),
    ),
    # 3. MiniMax — Anthropic 兼容接口,不支持 prompt_cache 和视觉
    ProviderPreset(
        name="MiniMax",
        protocol="anthropic",
        base_url="https://api.minimaxi.com/anthropic",
        model_id="MiniMax-M2.7",
        description="MiniMax 大模型 — Anthropic 兼容接口,支持流式工具",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=False,
        ),
    ),
    # 4. DeepSeek — OpenAI 兼容接口,推理模型不支持视觉
    ProviderPreset(
        name="DeepSeek",
        protocol="openai",
        base_url="https://api.deepseek.com/v1",
        model_id="deepseek-chat",
        description="DeepSeek 官方 API — OpenAI 兼容,支持流式工具,DeepSeek-R1 支持推理",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=False,
        ),
    ),
    # 5. Kimi (Moonshot AI) — OpenAI 兼容接口,支持长上下文
    ProviderPreset(
        name="Kimi (Moonshot)",
        protocol="openai",
        base_url="https://api.moonshot.cn/v1",
        model_id="moonshot-v1-8k",
        description="Moonshot Kimi — OpenAI 兼容,长上下文支持(8k/32k/128k),支持视觉",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=True,
        ),
    ),
    # 6. Qwen 通义千问 (Alibaba Cloud) — OpenAI 兼容接口
    ProviderPreset(
        name="Qwen (通义千问)",
        protocol="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_id="qwen-plus",
        description="阿里云通义千问 — OpenAI 兼容接口,qwen-plus / qwen-turbo / qwen-vl-max",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=False,
        ),
    ),
    # 7. 智谱 AI (GLM-4) — OpenAI 兼容接口
    ProviderPreset(
        name="智谱 AI (GLM)",
        protocol="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model_id="glm-4-flash",
        description="智谱 GLM-4 — OpenAI 兼容,支持函数调用 / 视觉",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=True,
        ),
    ),
    # 8. Google Gemini (OpenAI-compatible endpoint)
    ProviderPreset(
        name="Google Gemini",
        protocol="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model_id="gemini-2.0-flash",
        description="Google Gemini — OpenAI 兼容接口,支持视觉 / 多模态",
        capabilities=ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,
            extended_thinking=False,
            vision=True,
        ),
    ),
]
