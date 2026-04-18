"""
可观测性中间件

post_turn 阶段记录每轮的关键指标:
- turn_count
- 工具调用数
- 耗时
通过 callback.harness_event 上报，Backend 写入 audit_logs。

pre_turn 记录 monotonic 起始时间；
post_turn 上报 callback.harness_event("turn_complete", {turn, duration_ms, tool_calls})。
tool_calls 从 ctx.custom_data.get("tool_call_count", 0) 读取（由 QueryEngine 在 post_turn 前填入）。

进程边界: 本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import time

import structlog

from executor.callbacks.backend_callback import BackendCallback
from executor.harness.middleware.base import Middleware, MiddlewareContext

logger = structlog.get_logger()


class ObservabilityMiddleware(Middleware):
    """可观测性中间件 — 记录每轮关键指标并上报。"""

    name: str = "observability"

    def __init__(self, callback: BackendCallback) -> None:
        self._callback = callback
        self._turn_start_time: float = 0.0

    async def pre_turn(self, ctx: MiddlewareContext) -> None:
        """记录本轮开始时间（monotonic clock，不受系统时间跳变影响）"""
        self._turn_start_time = time.monotonic()

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """上报本轮关键指标"""
        duration_ms = int((time.monotonic() - self._turn_start_time) * 1000)
        # tool_call_count 由 QueryEngine 在 post_turn 前写入 custom_data
        tool_calls = ctx.custom_data.get("tool_call_count", 0)

        logger.info(
            "harness.observability.turn_complete",
            run_id=ctx.run_id,
            turn=ctx.turn_count,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
        )

        await self._callback.harness_event(
            "turn_complete",
            {
                "turn": ctx.turn_count,
                "duration_ms": duration_ms,
                "tool_calls": tool_calls,
            },
        )
