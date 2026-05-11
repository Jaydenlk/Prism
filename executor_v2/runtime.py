from __future__ import annotations

from typing import Any

import structlog
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    HookMatcher,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from executor_v2.callbacks import BackendCallback
from executor_v2.config import RunConfig
from executor_v2.hooks.prism_hook import PrismHooks

logger = structlog.get_logger(__name__)


class PrismAgentRuntime:
    def __init__(
        self, config: RunConfig, callback: BackendCallback, hooks: PrismHooks
    ) -> None:
        self._config = config
        self._callback = callback
        self._hooks = hooks
        self._client: ClaudeSDKClient | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        env: dict[str, str] = {"ANTHROPIC_API_KEY": self._config.api_key}
        if self._config.base_url:
            env["ANTHROPIC_BASE_URL"] = self._config.base_url

        system_prompt: dict[str, Any] | None = None
        if self._config.system_prompt:
            system_prompt = {
                "type": "preset",
                "preset": "claude_code",
                "append": self._config.system_prompt,
            }

        return ClaudeAgentOptions(
            model=self._config.model,
            system_prompt=system_prompt,
            permission_mode="bypassPermissions",
            max_turns=self._config.max_turns,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            env=env,
            include_partial_messages=True,
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher=None, hooks=[self._hooks.on_pre_tool_use])
                ],
                "PostToolUse": [
                    HookMatcher(matcher=None, hooks=[self._hooks.on_post_tool_use])
                ],
                "PostToolUseFailure": [
                    HookMatcher(
                        matcher=None, hooks=[self._hooks.on_post_tool_use_failure]
                    )
                ],
            },
        )

    async def run(self) -> None:
        options = self._build_options()
        self._client = ClaudeSDKClient(options=options)
        log = logger.bind(run_id=self._config.run_id)

        try:
            await self._client.connect()
            log.info("sdk_connected")
            await self._client.query(
                self._config.prompt, session_id=self._config.session_id
            )
            async for msg in self._client.receive_response():
                await self._handle_message(msg)
        except Exception:
            log.exception("runtime_error")
            raise
        finally:
            if self._client:
                await self._client.disconnect()
                log.info("sdk_disconnected")

    async def _handle_message(self, msg: object) -> None:
        if isinstance(msg, StreamEvent):
            await self._on_stream_event(msg)
        elif isinstance(msg, AssistantMessage):
            await self._on_assistant_message(msg)
        elif isinstance(msg, ResultMessage):
            await self._on_result(msg)

    async def _on_stream_event(self, event: StreamEvent) -> None:
        raw = event.event
        if raw.get("type") != "content_block_delta":
            return
        delta = raw.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text:
                await self._callback.text_delta(text, event.uuid)

    async def _on_assistant_message(self, msg: AssistantMessage) -> None:
        blocks: list[dict[str, Any]] = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ThinkingBlock):
                blocks.append({"type": "thinking", "thinking": block.thinking})
            elif isinstance(block, ToolUseBlock):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
            elif isinstance(block, ToolResultBlock):
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error,
                    }
                )
        if blocks:
            await self._callback.message_complete("assistant", blocks)

    async def _on_result(self, msg: ResultMessage) -> None:
        usage = msg.usage or {}
        if msg.is_error:
            await self._callback.run_error(msg.result or "Unknown error")
        else:
            await self._callback.run_complete(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_hit_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                turn_count=msg.num_turns,
            )

    async def interrupt(self) -> None:
        if self._client:
            await self._client.interrupt()
