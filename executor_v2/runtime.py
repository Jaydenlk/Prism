from __future__ import annotations

from typing import Any

import structlog
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from executor_v2.callbacks import BackendCallback
from executor_v2.config import RunConfig
from executor_v2.hooks.registry import (
    HookRegistry,
    MESSAGE_COMPLETE,
    RUN_COMPLETE,
    RUN_ERROR,
    SESSION_END,
    SESSION_START,
    TEXT_DELTA,
)
from executor_v2.hooks.sdk_bridge import SDKBridge

logger = structlog.get_logger(__name__)

Message = StreamEvent | AssistantMessage | ResultMessage


class PrismAgentRuntime:
    def __init__(
        self,
        config: RunConfig,
        callback: BackendCallback,
        registry: HookRegistry,
        memory_prompt: str = "",
    ) -> None:
        self._config = config
        self._callback = callback
        self._registry = registry
        self._bridge = SDKBridge(registry)
        self._memory_prompt = memory_prompt
        self._client: ClaudeSDKClient | None = None
        self._last_confidence: str | None = None
        self._last_uncertain_claims: list[str] | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        env: dict[str, str] = {"ANTHROPIC_API_KEY": self._config.api_key}
        if self._config.base_url:
            env["ANTHROPIC_BASE_URL"] = self._config.base_url

        combined = self._config.system_prompt
        if self._memory_prompt:
            combined = f"{combined}\n\n{self._memory_prompt}".strip() if combined else self._memory_prompt

        system_prompt: dict[str, Any] | None = None
        if combined:
            system_prompt = {
                "type": "preset",
                "preset": "claude_code",
                "append": combined,
            }

        resume_id = self._config.session_id if self._config.resume_from_step is not None else None

        return ClaudeAgentOptions(
            model=self._config.model,
            cwd=self._config.workspace_path,
            system_prompt=system_prompt,
            permission_mode="acceptEdits",
            max_turns=self._config.max_turns,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            env=env,
            include_partial_messages=True,
            hooks=self._bridge.build_sdk_hooks(),
            resume=resume_id,
        )

    async def run(self) -> None:
        options = self._build_options()
        self._client = ClaudeSDKClient(options=options)
        log = logger.bind(run_id=self._config.run_id)

        await self._registry.fire(SESSION_START, {
            "run_id": self._config.run_id,
            "session_id": self._config.session_id,
            "user_id": self._config.user_id,
            "model": self._config.model,
        })

        try:
            await self._client.connect()
            log.info("sdk_connected")
            await self._client.query(
                self._config.prompt, session_id=self._config.session_id
            )
            async for msg in self._client.receive_response():
                await self._handle_message(msg)
        except Exception as exc:
            log.exception("runtime_error")
            await self._registry.fire(RUN_ERROR, {
                "run_id": self._config.run_id,
                "error": str(exc),
            })
            raise
        finally:
            await self._registry.fire(SESSION_END, {
                "run_id": self._config.run_id,
                "session_id": self._config.session_id,
                "user_id": self._config.user_id,
            })
            if self._client:
                await self._client.disconnect()
                log.info("sdk_disconnected")

    async def _handle_message(self, msg: Message) -> None:
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
                await self._registry.fire(TEXT_DELTA, {"text": text, "uuid": event.uuid})

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
            payload = {"role": "assistant", "blocks": blocks}
            await self._registry.fire(MESSAGE_COMPLETE, payload)
            conf = payload.get("_confidence")
            claims = payload.get("_uncertain_claims")
            if conf is not None:
                self._last_confidence = conf
                self._last_uncertain_claims = claims
            await self._callback.message_complete(
                "assistant", blocks,
                confidence=conf,
                uncertain_claims=claims,
            )

    async def _on_result(self, msg: ResultMessage) -> None:
        usage = msg.usage or {}
        if msg.is_error:
            await self._callback.run_error(msg.result or "Unknown error")
            await self._registry.fire(RUN_ERROR, {"error": msg.result})
        else:
            harness: dict[str, Any] = {}
            if self._last_confidence is not None:
                harness["confidence"] = self._last_confidence
            if self._last_uncertain_claims:
                harness["uncertain_claims"] = self._last_uncertain_claims
            await self._callback.run_complete(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_hit_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                turn_count=msg.num_turns,
                harness_summary=harness,
            )
            await self._registry.fire(RUN_COMPLETE, {
                "usage": usage,
                "num_turns": msg.num_turns,
            })

    async def interrupt(self) -> None:
        if self._client:
            await self._client.interrupt()
