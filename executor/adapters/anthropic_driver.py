"""
Prism v2 Model Adapter Layer — Anthropic Messages API Driver

实现 ADR-007 canonical Anthropic 语义:
- PrismMessage 直接映射到 Anthropic API messages 格式(无需 role 转换)
- tool_result 天然位于 user message 的 content block 中

实现 ADR-008:按 ProviderCapabilities 决定是否注入 cache_control。
实现 ADR-009:使用 Anthropic SDK count_tokens(),失败 fallback tiktoken + WARNING。
实现 ADR-022:text_delta / tool_use_delta 直接 PUBLISH 到 Redis `sse:{session_id}`。
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

import httpx

from executor.adapters.base import (
    ContentBlock,
    ModelAdapter,
    ModelResponse,
    PrismMessage,
    ProviderCapabilities,
    StreamEvent,
    TextBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
)
from executor.adapters.stream_parser import parse_sse_lines
from executor.engine.prompt_assembler import CACHE_BOUNDARY_MARKER

logger = logging.getLogger(__name__)

# Anthropic API 版本
_ANTHROPIC_API_VERSION = "2023-06-01"

# HTTP 超时:30s 连接,300s 读取(长流式响应)
import os as _os
_CONNECT_TIMEOUT = 30.0
_READ_TIMEOUT = float(_os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "300"))


class AnthropicDriver(ModelAdapter):
    """
    Anthropic Messages API Driver。

    PrismMessage(canonical Anthropic 语义) → Anthropic API messages 格式。
    流式响应 → StreamEvent 序列 + Redis PUBLISH(ADR-022)。

    v4 特性:
    - cache_control 注入(ADR-008,需 capabilities.prompt_cache=True)
    - Redis 直通 PUBLISH(ADR-022,绕过 Backend HTTP 回调)
    - 精确 token 计数(ADR-009,Anthropic SDK count_tokens)
    - cache tokens 解析(usage.cache_read_input_tokens / cache_creation_input_tokens)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        capabilities: ProviderCapabilities | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(base_url, api_key, model, capabilities, **kwargs)
        # Redis 连接惰性初始化(首次 stream 时创建,避免导入时连接)
        self._redis: object | None = None

    async def _get_redis(self) -> object | None:
        """惰性初始化 Redis 连接(子进程环境变量 REDIS_URL)。"""
        if self._redis is not None:
            return self._redis
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            logger.warning(
                "REDIS_URL not set in environment; Redis publish disabled"
            )
            return None
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            self._redis = aioredis.from_url(
                redis_url, encoding="utf-8", decode_responses=True
            )
            return self._redis
        except Exception as exc:
            logger.error("Failed to connect to Redis: %s", exc)
            return None

    async def _publish_event(
        self, redis_client: object | None, session_id: str | None, payload: dict
    ) -> None:
        """向 Redis channel `sse:{session_id}` 发布事件(ADR-022)。"""
        if redis_client is None or session_id is None:
            return
        try:
            channel = f"sse:{session_id}"
            await redis_client.publish(channel, json.dumps(payload))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Redis publish failed: %s", exc)

    # ------------------------------------------------------------------
    # 消息格式转换
    # ------------------------------------------------------------------

    def _convert_block_to_anthropic(self, block: ContentBlock) -> dict:
        """将单个 ContentBlock 转换为 Anthropic API block dict。"""
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        elif isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        elif isinstance(block, ToolResultBlock):
            # v4: tool_result 天然在 user message 里,无需角色转换
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }
        else:
            # 未知类型安全降级为文本
            logger.warning("Unknown ContentBlock type: %s", type(block).__name__)
            return {"type": "text", "text": str(block)}

    def _convert_messages_to_anthropic(
        self, messages: list[PrismMessage]
    ) -> list[dict]:
        """
        将 PrismMessage 列表转换为 Anthropic API messages 格式。

        因为 PrismMessage 已是 canonical Anthropic 语义,转换相当直接:
        - role 直接映射(user/assistant)
        - content blocks 逐一转换
        """
        result = []
        for msg in messages:
            blocks = [self._convert_block_to_anthropic(b) for b in msg.content]
            result.append({"role": msg.role, "content": blocks})
        return result

    def _convert_tools_to_anthropic(self, tools: list[ToolDefinition]) -> list[dict]:
        """将 ToolDefinition 列表转换为 Anthropic API tools 格式。"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

    def _build_system_blocks(self, system_prompt: str) -> list[dict]:
        """按 CACHE_BOUNDARY_MARKER 拆分 system_prompt 为静态/动态两个 text block。

        静态前缀每轮字节级一致，Anthropic Prompt Cache 可命中。
        动态后缀每轮可能变化，不加 cache_control。
        """
        if CACHE_BOUNDARY_MARKER in system_prompt:
            static, dynamic = system_prompt.split(CACHE_BOUNDARY_MARKER, 1)
            blocks = [{"type": "text", "text": static}]
            if dynamic.strip():
                blocks.append({"type": "text", "text": dynamic})
            return blocks
        return [{"type": "text", "text": system_prompt}]

    def _inject_cache_control(
        self,
        system_blocks: list[dict],
        messages: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """注入 cache_control（ADR-008）。

        策略：
        1. system 第一个 text block 加 cache_control（静态前缀，字节级一致）
        2. 最后一条 user message 的最后一个 text block 加 cache_control
        """
        if system_blocks:
            for block in system_blocks:
                if block.get("type") == "text":
                    block["cache_control"] = {"type": "ephemeral"}
                    break

        for msg in reversed(messages):
            if msg["role"] == "user":
                for block in reversed(msg["content"]):
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["cache_control"] = {"type": "ephemeral"}
                        break
                break

        return system_blocks, messages

    # ------------------------------------------------------------------
    # stream()
    # ------------------------------------------------------------------

    async def stream(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        session_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        流式调用 Anthropic Messages API。

        ADR-022:text_delta / tool_use_delta 事件在 yield 前立即 PUBLISH 到
        Redis channel `sse:{session_id}`,绕过 Backend HTTP 回调。
        session_id=None 时跳过 publish(单测场景)。
        """
        # 工具排序(字母表顺序,保证 Prompt Cache 前缀稳定)
        sorted_tools = self._sort_tools(tools)

        # 转换消息格式
        anthropic_messages = self._convert_messages_to_anthropic(messages)

        # 构建 system blocks（按 CACHE_BOUNDARY_MARKER 拆分静态/动态）
        system_blocks = self._build_system_blocks(system_prompt)

        # Cache control 注入(ADR-008)
        if self.capabilities.prompt_cache:
            system_blocks, anthropic_messages = self._inject_cache_control(
                system_blocks, anthropic_messages
            )

        # 构建请求 body
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": anthropic_messages,
            "stream": True,
        }
        if sorted_tools:
            body["tools"] = self._convert_tools_to_anthropic(sorted_tools)

        # 请求头
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }

        # Redis 连接(惰性初始化)
        redis_client = await self._get_redis() if session_id else None

        url = f"{self.base_url}/v1/messages"
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=30.0, pool=5.0)

        # 当前工具调用状态追踪
        current_tool_id: str = ""
        current_tool_name: str = ""
        current_tool_delta_parts: list[str] = []
        in_tool_use: bool = False

        # usage 信息(从 message_start / message_delta 收集)
        input_tokens: int = 0
        output_tokens: int = 0
        cache_read_tokens: int = 0
        cache_creation_tokens: int = 0
        stop_reason: str = ""

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream(
                    "POST", url, json=body, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        error_body = await response.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        yield StreamEvent(
                            type="error",
                            error_message=f"HTTP {response.status_code}: {error_text[:500]}",
                        )
                        return

                    async for event_type, data in parse_sse_lines(response):
                        # 处理 SSE 解析层的 error 事件
                        if event_type == "error":
                            raw = data.get("raw", "")
                            yield StreamEvent(
                                type="error",
                                error_message=f"json_parse_failed: {raw[:200]}",
                            )
                            continue

                        event_name = data.get("type", "")

                        if event_name == "message_start":
                            # 从 message_start 收集初始 usage
                            usage = data.get("message", {}).get("usage", {})
                            input_tokens = usage.get("input_tokens", 0)
                            cache_read_tokens = usage.get(
                                "cache_read_input_tokens", 0
                            )
                            cache_creation_tokens = usage.get(
                                "cache_creation_input_tokens", 0
                            )

                        elif event_name == "content_block_start":
                            cb = data.get("content_block", {})
                            cb_type = cb.get("type", "")
                            if cb_type == "text":
                                in_tool_use = False
                                # content_block_start 的 text 通常为空,等待 delta
                            elif cb_type == "tool_use":
                                in_tool_use = True
                                current_tool_id = cb.get("id", "")
                                current_tool_name = cb.get("name", "")
                                current_tool_delta_parts = []
                                event = StreamEvent(
                                    type="tool_use_start",
                                    tool_use_id=current_tool_id,
                                    tool_name=current_tool_name,
                                )
                                yield event

                        elif event_name == "content_block_delta":
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")

                            if delta_type == "text_delta":
                                text_content = delta.get("text", "")
                                event = StreamEvent(
                                    type="text_delta", text=text_content
                                )
                                # ADR-022: PUBLISH 前 yield(并发 publish)
                                publish_payload = {
                                    "type": "text_delta",
                                    "text": text_content,
                                    "session_id": session_id,
                                }
                                await self._publish_event(
                                    redis_client, session_id, publish_payload
                                )
                                yield event

                            elif delta_type == "input_json_delta":
                                partial = delta.get("partial_json", "")
                                current_tool_delta_parts.append(partial)
                                event = StreamEvent(
                                    type="tool_use_delta",
                                    tool_use_id=current_tool_id,
                                    tool_name=current_tool_name,
                                    tool_input_delta=partial,
                                )
                                publish_payload = {
                                    "type": "tool_use_delta",
                                    "tool_use_id": current_tool_id,
                                    "tool_name": current_tool_name,
                                    "tool_input_delta": partial,
                                    "session_id": session_id,
                                }
                                await self._publish_event(
                                    redis_client, session_id, publish_payload
                                )
                                yield event

                        elif event_name == "content_block_stop":
                            if in_tool_use:
                                # 拼接完整工具参数 JSON
                                full_json_str = "".join(current_tool_delta_parts)
                                tool_input_complete: dict = {}
                                if full_json_str.strip():
                                    try:
                                        tool_input_complete = json.loads(full_json_str)
                                    except json.JSONDecodeError:
                                        # json_repair 兜底
                                        try:
                                            import json_repair  # type: ignore[import]

                                            repaired = json_repair.repair_json(
                                                full_json_str
                                            )
                                            tool_input_complete = json.loads(repaired)
                                        except Exception:
                                            logger.warning(
                                                "Failed to parse tool input JSON: %s",
                                                full_json_str[:200],
                                            )
                                yield StreamEvent(
                                    type="tool_use_end",
                                    tool_use_id=current_tool_id,
                                    tool_name=current_tool_name,
                                    tool_input_complete=tool_input_complete,
                                )
                                in_tool_use = False

                        elif event_name == "message_delta":
                            # stop_reason 和增量 usage
                            delta = data.get("delta", {})
                            stop_reason = delta.get("stop_reason", "")
                            usage = data.get("usage", {})
                            output_tokens = usage.get("output_tokens", output_tokens)

                        elif event_name == "message_stop":
                            # 流结束:发送 message_end 事件
                            yield StreamEvent(
                                type="message_end",
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cache_hit_tokens=cache_read_tokens,
                                cache_creation_tokens=cache_creation_tokens,
                                stop_reason=stop_reason,
                            )

                        elif event_name == "error":
                            error_obj = data.get("error", {})
                            yield StreamEvent(
                                type="error",
                                error_message=f"Anthropic API error: {error_obj}",
                            )

            except httpx.TimeoutException as exc:
                yield StreamEvent(
                    type="error",
                    error_message=f"Request timeout: {exc}",
                )
            except httpx.RequestError as exc:
                yield StreamEvent(
                    type="error",
                    error_message=f"Request error: {exc}",
                )

    # ------------------------------------------------------------------
    # complete()
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """非流式调用 Anthropic Messages API。"""
        sorted_tools = self._sort_tools(tools)
        anthropic_messages = self._convert_messages_to_anthropic(messages)
        system_blocks = self._build_system_blocks(system_prompt)

        if self.capabilities.prompt_cache:
            system_blocks, anthropic_messages = self._inject_cache_control(
                system_blocks, anthropic_messages
            )

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": anthropic_messages,
            "stream": False,
        }
        if sorted_tools:
            body["tools"] = self._convert_tools_to_anthropic(sorted_tools)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/v1/messages"
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=30.0, pool=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

        # 解析响应
        stop_reason = data.get("stop_reason", "")
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)

        # 解析 content 为 PrismMessage
        response_blocks: list[ContentBlock] = []
        for block in data.get("content", []):
            btype = block.get("type", "")
            if btype == "text":
                response_blocks.append(TextBlock(text=block.get("text", "")))
            elif btype == "tool_use":
                response_blocks.append(
                    ToolUseBlock(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        input=block.get("input", {}),
                    )
                )

        assistant_msg = PrismMessage(role="assistant", content=response_blocks)

        return ModelResponse(
            messages=[assistant_msg],
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )

    # ------------------------------------------------------------------
    # count_tokens()
    # ------------------------------------------------------------------

    def count_tokens(
        self,
        messages: list[PrismMessage],
        system_prompt: str = "",
    ) -> int:
        """
        精确 token 计数(ADR-009)。

        优先使用 Anthropic SDK count_tokens() API。
        Provider 不支持该端点(如 MiniMax 等兼容实现)时,
        fallback 到 tiktoken cl100k_base + log WARNING。
        """
        try:
            from anthropic import Anthropic  # type: ignore[import]

            client = Anthropic(api_key=self.api_key, base_url=self.base_url)
            anthropic_messages = self._convert_messages_to_anthropic(messages)
            result = client.messages.count_tokens(
                model=self.model,
                messages=anthropic_messages,  # type: ignore[arg-type]
                system=system_prompt,
            )
            return result.input_tokens
        except Exception as exc:
            logger.warning(
                "Anthropic count_tokens() failed (fallback tiktoken): %s", exc
            )
            return self._count_tokens_tiktoken_fallback(messages, system_prompt)

    def _count_tokens_tiktoken_fallback(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> int:
        """tiktoken fallback:cl100k_base 编码,粗略估计。"""
        try:
            import tiktoken  # type: ignore[import]

            enc = tiktoken.get_encoding("cl100k_base")
            text_parts = [system_prompt]
            for msg in messages:
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolResultBlock):
                        text_parts.append(block.content)
                    elif isinstance(block, ToolUseBlock):
                        text_parts.append(json.dumps(block.input))
            full_text = "\n".join(text_parts)
            return len(enc.encode(full_text))
        except Exception as exc:
            logger.error("tiktoken fallback also failed: %s", exc)
            # 最后兜底:字符数 / 4(极粗略)
            all_text = system_prompt + "".join(
                b.text if isinstance(b, TextBlock) else ""
                for m in messages
                for b in m.content
            )
            return max(1, len(all_text) // 4)
