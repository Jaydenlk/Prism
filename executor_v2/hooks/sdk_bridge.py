from __future__ import annotations

from typing import Any

from claude_agent_sdk.types import HookMatcher

from executor_v2.hooks.registry import (
    HookRegistry,
    NOTIFICATION,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    POST_TOOL_USE_FAILURE,
    PRE_COMPACT,
    PRE_TOOL_USE,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    USER_PROMPT_SUBMIT,
)

_SDK_EVENTS: list[str] = [
    PRE_TOOL_USE,
    POST_TOOL_USE,
    POST_TOOL_USE_FAILURE,
    USER_PROMPT_SUBMIT,
    STOP,
    SUBAGENT_STOP,
    PRE_COMPACT,
    NOTIFICATION,
    SUBAGENT_START,
    PERMISSION_REQUEST,
]


class SDKBridge:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    def build_sdk_hooks(self) -> dict[str, list[HookMatcher]]:
        result: dict[str, list[HookMatcher]] = {}
        for event in _SDK_EVENTS:
            captured_event = event

            async def _callback(
                input_data: dict[str, Any],
                tool_use_id: str | None,
                context: dict[str, Any],
                _event: str = captured_event,
            ) -> dict[str, Any]:
                payload = dict(input_data)
                if tool_use_id is not None:
                    payload.setdefault("tool_use_id", tool_use_id)
                results = await self._registry.fire(_event, payload)
                for r in results:
                    if r.get("decision") == "block":
                        return r
                    if r.get("continue_") is False:
                        return r
                return {"continue_": True}

            result[event] = [HookMatcher(matcher=None, hooks=[_callback])]
        return result
