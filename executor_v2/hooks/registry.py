from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = structlog.get_logger(__name__)

SESSION_START = "SessionStart"
SESSION_END = "SessionEnd"
PRE_TOOL_USE = "PreToolUse"
POST_TOOL_USE = "PostToolUse"
POST_TOOL_USE_FAILURE = "PostToolUseFailure"
USER_PROMPT_SUBMIT = "UserPromptSubmit"
STOP = "Stop"
SUBAGENT_STOP = "SubagentStop"
PRE_COMPACT = "PreCompact"
NOTIFICATION = "Notification"
SUBAGENT_START = "SubagentStart"
PERMISSION_REQUEST = "PermissionRequest"
TEXT_DELTA = "TextDelta"
MESSAGE_COMPLETE = "MessageComplete"
RUN_COMPLETE = "RunComplete"
RUN_ERROR = "RunError"

_BLOCKING_CATEGORIES = {"permission", "guardrail", "safety"}


@dataclass
class HookHandler:
    callback: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    priority: int = 100
    category: str = "observability"


class HookRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        self._handlers.setdefault(event, []).append(handler)
        self._handlers[event].sort(key=lambda h: h.priority)

    async def fire(self, event: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        payload["_event"] = event
        handlers = self._handlers.get(event, [])
        results: list[dict[str, Any]] = []
        for handler in handlers:
            blocking = handler.category in _BLOCKING_CATEGORIES
            try:
                result = await handler.callback(payload)
                results.append(result)
                if blocking and (
                    result.get("decision") == "block"
                    or result.get("continue_") is False
                ):
                    break
            except Exception as exc:
                logger.warning(
                    "hook_handler_error",
                    hook_event=event,
                    category=handler.category,
                    error=str(exc),
                )
                if blocking:
                    raise
        return results
