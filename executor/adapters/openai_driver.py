"""
Prism v2 Model Adapter Layer — OpenAI Chat Completions API Driver

实现 ADR-007 展开规则:
- PrismMessage(role="user", content=[ToolResultBlock(A), ToolResultBlock(B)]) 展开为:
  {"role": "tool", "tool_call_id": "A", "content": "结果 A"}
  {"role": "tool", "tool_call_id": "B", "content": "结果 B"}
- 混合情况(ToolResult + TextBlock):先展开所有 tool_result 为 role=tool 消息,
  最后追加一条 role=user 消息带 TextBlock 内容

实现 ADR-008:按 ProviderCapabilities 调整请求(OpenAI 不支持 prompt_cache)。
实现 ADR-009:使用 tiktoken 精确计数;未知模型 fallback cl100k_base + WARNING。
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

logger = logging.getLogger(__name__)

# HTTP 超时
_CONNECT_TIMEOUT = 30.0
_READ_TIMEOUT = 300.0

# per-message token overhead(OpenAI tiktoken 约定)
_TOKENS_PER_MESSAGE = 4
_TOKENS_REPLY_PRIMING = 3


class OpenAIDriver(ModelAdapter):
    """
    OpenAI Chat Completions API Driver。

    ADR-007 展开规则:
    含 tool_result 的 user PrismMessage → 多条 role=tool 消息 + 可选 role=user 消息。

    v4 特性:
    - Redis 直通 PUBLISH(ADR-022)
    - tiktoken 精确 token 计数(ADR-009)
    - OpenAI 不支持 prompt_cache,cache_* tokens 恒为 0
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
    # 消息格式转换(ADR-007 展开规则)
    # ------------------------------------------------------------------

    def _convert_messages_to_openai(
        self, messages: list[PrismMessage], system_prompt: str
    ) -> list[dict]:
        """
        将 PrismMessage 列表 + system_prompt 转换为 OpenAI Chat Completions messages 格式。

        ADR-007 展开规则(关键):
        1. system_prompt → {"role": "system", "content": system_prompt}(首条)
        2. user message 含纯 TextBlock → {"role": "user", "content": text}
        3. assistant message 含 ToolUseBlock → {"role": "assistant", "content": text|null,
           "tool_calls": [...]}
        4. user message 含 ToolResultBlock → 展开为多条 {"role": "tool", ...}
        5. 混合情况(ToolResult + Text):先展开所有 tool_result,最后追加 role=user 文本

        验收示例(ADR-007):
          PrismMessage(role="user", content=[ToolResultBlock(A), ToolResultBlock(B), TextBlock("然后")])
          →
          {"role": "tool", "tool_call_id": "A", "content": "结果 A"}
          {"role": "tool", "tool_call_id": "B", "content": "结果 B"}
          {"role": "user", "content": "然后"}
        """
        result: list[dict] = []

        # system 作为第一条消息
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "user":
                result.extend(self._convert_user_message_to_openai(msg))
            elif msg.role == "assistant":
                result.append(self._convert_assistant_message_to_openai(msg))

        return result

    def _convert_user_message_to_openai(self, msg: PrismMessage) -> list[dict]:
        """
        将 user PrismMessage 转换为 OpenAI 格式(可能展开为多条消息)。

        ADR-007 展开规则:
        - 仅 TextBlock → 单条 role=user
        - 含 ToolResultBlock → 每个 ToolResultBlock 展开为独立 role=tool 消息
        - 混合(ToolResult + Text):先展开所有 tool_result,最后追加 role=user 文本
        """
        tool_result_msgs: list[dict] = []
        text_parts: list[str] = []

        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                tool_result_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": block.content,
                    }
                )
            elif isinstance(block, TextBlock):
                text_parts.append(block.text)
            else:
                # ToolUseBlock 不应出现在 user message 中
                logger.warning(
                    "Unexpected block type %s in user message", type(block).__name__
                )

        output: list[dict] = []

        # 先输出所有 tool_result(role=tool)
        output.extend(tool_result_msgs)

        # 有 text 内容时追加 role=user(仅当有非空文本)
        combined_text = "\n".join(t for t in text_parts if t.strip())
        if combined_text:
            output.append({"role": "user", "content": combined_text})
        elif not tool_result_msgs:
            # 完全空消息:保留一条空 user 消息,避免 API 报错
            output.append({"role": "user", "content": ""})

        return output

    def _convert_assistant_message_to_openai(self, msg: PrismMessage) -> dict:
        """
        将 assistant PrismMessage 转换为 OpenAI 格式。

        assistant 消息可能同时包含文本和工具调用:
        {"role": "assistant", "content": text_or_null, "tool_calls": [...]}
        """
        text_parts: list[str] = []
        tool_calls: list[dict] = []

        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )
            else:
                logger.warning(
                    "Unexpected block type %s in assistant message",
                    type(block).__name__,
                )

        content_text: str | None = "\n".join(text_parts) if text_parts else None

        openai_msg: dict = {"role": "assistant", "content": content_text}
        if tool_calls:
            openai_msg["tool_calls"] = tool_calls

        return openai_msg

    def _convert_tools_to_openai(self, tools: list[ToolDefinition]) -> list[dict]:
        """将 ToolDefinition 列表转换为 OpenAI function calling tools 格式。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

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
        流式调用 OpenAI Chat Completions API。

        ADR-022:text_delta / tool_use_delta 在 yield 前 PUBLISH 到 Redis。
        session_id=None 时跳过 publish(单测场景)。
        """
        # 工具排序(字母表顺序)
        sorted_tools = self._sort_tools(tools)

        # 转换消息格式(含 ADR-007 展开)
        openai_messages = self._convert_messages_to_openai(messages, system_prompt)

        # 构建请求 body
        body: dict = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
        }
        if sorted_tools:
            body["tools"] = self._convert_tools_to_openai(sorted_tools)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Redis 连接
        redis_client = await self._get_redis() if session_id else None

        url = f"{self.base_url}/chat/completions"
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=30.0, pool=5.0)

        # 工具调用状态(多工具并行:按 index 追踪)
        # tool_calls_map: index → {id, name, delta_parts}
        tool_calls_map: dict[int, dict] = {}

        # usage 信息
        input_tokens: int = 0
        output_tokens: int = 0
        stop_reason: str = ""
        finish_reason_seen: bool = False

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
                        # 处理 SSE 解析层 error 事件
                        if event_type == "error":
                            raw = data.get("raw", "")
                            yield StreamEvent(
                                type="error",
                                error_message=f"json_parse_failed: {raw[:200]}",
                            )
                            continue

                        # 处理 OpenAI usage chunk(最后一个无 choices 的 chunk)
                        if "usage" in data and not data.get("choices"):
                            usage = data.get("usage", {})
                            input_tokens = usage.get("prompt_tokens", input_tokens)
                            output_tokens = usage.get(
                                "completion_tokens", output_tokens
                            )
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish = choice.get("finish_reason")

                        # 文本 delta
                        text_content = delta.get("content")
                        if text_content:
                            event = StreamEvent(type="text_delta", text=text_content)
                            publish_payload = {
                                "type": "text_delta",
                                "text": text_content,
                                "session_id": session_id,
                            }
                            await self._publish_event(
                                redis_client, session_id, publish_payload
                            )
                            yield event

                        # 工具调用 delta(OpenAI 增量拼接)
                        tool_calls_delta = delta.get("tool_calls", [])
                        for tc in tool_calls_delta:
                            idx = tc.get("index", 0)
                            tc_id = tc.get("id", "")
                            func = tc.get("function", {})
                            tc_name = func.get("name", "")
                            tc_args_delta = func.get("arguments", "")

                            if idx not in tool_calls_map:
                                # 首次出现:tool_use_start
                                tool_calls_map[idx] = {
                                    "id": tc_id,
                                    "name": tc_name,
                                    "delta_parts": [],
                                }
                                yield StreamEvent(
                                    type="tool_use_start",
                                    tool_use_id=tc_id,
                                    tool_name=tc_name,
                                )
                            else:
                                # 更新 id/name(可能在后续 chunk 中补全)
                                if tc_id:
                                    tool_calls_map[idx]["id"] = tc_id
                                if tc_name:
                                    tool_calls_map[idx]["name"] = tc_name

                            if tc_args_delta:
                                tool_calls_map[idx]["delta_parts"].append(tc_args_delta)
                                current_id = tool_calls_map[idx]["id"]
                                current_name = tool_calls_map[idx]["name"]
                                event = StreamEvent(
                                    type="tool_use_delta",
                                    tool_use_id=current_id,
                                    tool_name=current_name,
                                    tool_input_delta=tc_args_delta,
                                )
                                publish_payload = {
                                    "type": "tool_use_delta",
                                    "tool_use_id": current_id,
                                    "tool_name": current_name,
                                    "tool_input_delta": tc_args_delta,
                                    "session_id": session_id,
                                }
                                await self._publish_event(
                                    redis_client, session_id, publish_payload
                                )
                                yield event

                        # usage 可能也在 choices chunk 里
                        if "usage" in data:
                            usage = data.get("usage", {})
                            if usage:
                                input_tokens = usage.get(
                                    "prompt_tokens", input_tokens
                                )
                                output_tokens = usage.get(
                                    "completion_tokens", output_tokens
                                )

                        # finish_reason
                        if finish and not finish_reason_seen:
                            finish_reason_seen = True
                            stop_reason = finish

                            # 先 yield 所有工具调用的 tool_use_end
                            for idx in sorted(tool_calls_map.keys()):
                                tc_info = tool_calls_map[idx]
                                full_args = "".join(tc_info["delta_parts"])
                                tool_input_complete: dict = {}
                                if full_args.strip():
                                    try:
                                        tool_input_complete = json.loads(full_args)
                                    except json.JSONDecodeError:
                                        try:
                                            import json_repair  # type: ignore[import]

                                            repaired = json_repair.repair_json(full_args)
                                            tool_input_complete = json.loads(repaired)
                                        except Exception:
                                            logger.warning(
                                                "Failed to parse tool args JSON: %s",
                                                full_args[:200],
                                            )
                                yield StreamEvent(
                                    type="tool_use_end",
                                    tool_use_id=tc_info["id"],
                                    tool_name=tc_info["name"],
                                    tool_input_complete=tool_input_complete,
                                )

                            yield StreamEvent(
                                type="message_end",
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                # OpenAI 不支持 prompt_cache
                                cache_hit_tokens=0,
                                cache_creation_tokens=0,
                                stop_reason=stop_reason,
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
        """非流式调用 OpenAI Chat Completions API。"""
        sorted_tools = self._sort_tools(tools)
        openai_messages = self._convert_messages_to_openai(messages, system_prompt)

        body: dict = {
            "model": self.model,
            "messages": openai_messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if sorted_tools:
            body["tools"] = self._convert_tools_to_openai(sorted_tools)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=30.0, pool=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        choice = data.get("choices", [{}])[0]
        stop_reason = choice.get("finish_reason", "")
        message = choice.get("message", {})

        # 解析响应内容为 PrismMessage(canonical Anthropic 语义)
        response_blocks: list[ContentBlock] = []
        content_text = message.get("content")
        if content_text:
            response_blocks.append(TextBlock(text=content_text))

        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            response_blocks.append(
                ToolUseBlock(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    input=args,
                )
            )

        assistant_msg = PrismMessage(role="assistant", content=response_blocks)

        return ModelResponse(
            messages=[assistant_msg],
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=0,  # OpenAI 不支持 prompt_cache
            cache_creation_tokens=0,
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
        精确 token 计数(ADR-009):使用 tiktoken。

        已知模型:tiktoken.encoding_for_model() 精确编码。
        未知模型(DeepSeek/Kimi/Qwen 等国产模型):fallback cl100k_base + log WARNING。
        """
        try:
            import tiktoken  # type: ignore[import]

            try:
                enc = tiktoken.encoding_for_model(self.model)
            except KeyError:
                logger.warning(
                    "tiktoken: unknown model '%s', falling back to cl100k_base. "
                    "Token count may be inaccurate — manual calibration recommended.",
                    self.model,
                )
                enc = tiktoken.get_encoding("cl100k_base")

            # 按 OpenAI tiktoken 约定计算
            # 参考:https://platform.openai.com/docs/guides/chat/managing-tokens
            total = _TOKENS_REPLY_PRIMING  # reply priming

            # system prompt
            if system_prompt:
                total += _TOKENS_PER_MESSAGE
                total += len(enc.encode(system_prompt))

            # 转换为 OpenAI 格式后计算(包含 ADR-007 展开)
            openai_messages = self._convert_messages_to_openai(messages, "")
            for oai_msg in openai_messages:
                total += _TOKENS_PER_MESSAGE
                role = oai_msg.get("role", "")
                total += len(enc.encode(role))
                content = oai_msg.get("content") or ""
                if content:
                    total += len(enc.encode(content))
                # tool_calls 参数
                for tc in oai_msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    total += len(enc.encode(func.get("name", "")))
                    total += len(enc.encode(func.get("arguments", "")))

            return total

        except Exception as exc:
            logger.error("tiktoken count_tokens failed: %s", exc)
            # 最终兜底:字符数 / 4
            all_text = system_prompt
            for msg in messages:
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        all_text += block.text
                    elif isinstance(block, ToolResultBlock):
                        all_text += block.content
            return max(1, len(all_text) // 4)
