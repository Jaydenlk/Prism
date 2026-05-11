from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from executor_v2.callbacks import BackendCallback

logger = structlog.get_logger(__name__)


class PrismHooks:
    def __init__(self, callback: BackendCallback) -> None:
        self._callback = callback
        self._tool_start_times: dict[str, float] = {}

    async def on_pre_tool_use(self, payload: dict[str, Any]) -> dict[str, Any]:
        tid = payload.get("tool_use_id", "")
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input") or {}
        self._tool_start_times[tid] = time.monotonic()
        try:
            await self._callback.tool_start(tid, tool_name, tool_input)
        except Exception as exc:
            logger.warning("hook_tool_start_failed", tool_use_id=tid, error=str(exc))
        return {"continue_": True}

    async def on_post_tool_use(self, payload: dict[str, Any]) -> dict[str, Any]:
        tid = payload.get("tool_use_id", "")
        tool_name = payload.get("tool_name", "")
        raw = payload.get("tool_response", "")
        output = str(raw)[:500]
        duration_ms = self._pop_duration_ms(tid)
        try:
            await self._callback.tool_end(tid, tool_name, output, False, duration_ms)
        except Exception as exc:
            logger.warning("hook_tool_end_failed", tool_use_id=tid, error=str(exc))
        return {"continue_": True}

    async def on_post_tool_use_failure(self, payload: dict[str, Any]) -> dict[str, Any]:
        tid = payload.get("tool_use_id", "")
        tool_name = payload.get("tool_name", "")
        error = str(payload.get("error", ""))[:500]
        duration_ms = self._pop_duration_ms(tid)
        try:
            await self._callback.tool_end(tid, tool_name, error, True, duration_ms)
        except Exception as exc:
            logger.warning("hook_tool_failure_failed", tool_use_id=tid, error=str(exc))
        return {"continue_": True}

    def _pop_duration_ms(self, tool_use_id: str) -> int:
        start = self._tool_start_times.pop(tool_use_id, None)
        if start is None:
            logger.warning("tool_end_without_start", tool_use_id=tool_use_id)
            return 0
        return int((time.monotonic() - start) * 1000)
