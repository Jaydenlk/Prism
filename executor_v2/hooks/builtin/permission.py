from __future__ import annotations

import uuid

import structlog

from executor_v2.callbacks import BackendCallback

logger = structlog.get_logger(__name__)

AUTO_ALLOW = frozenset({"Read", "Grep", "Glob", "Ls", "WebSearch", "WebFetch"})


class PermissionController:
    def __init__(self, callback: BackendCallback) -> None:
        self._callback = callback

    async def check(self, payload: dict) -> dict:
        tool_name = payload.get("tool_name", "")

        if tool_name in AUTO_ALLOW:
            return {"continue_": True}

        request_id = str(uuid.uuid4())
        logger.info("permission.asking", tool=tool_name, request_id=request_id)

        decision = await self._callback.permission_ask(
            request_id=request_id,
            tool_name=tool_name,
            tool_input=payload.get("tool_input", {}),
        )

        logger.info("permission.answered", tool=tool_name, decision=decision)

        if decision in ("allow", "approve", "yes"):
            return {"continue_": True}
        return {"continue_": False, "decision": "deny", "reason": f"User denied {tool_name}"}
