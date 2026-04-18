"""
MiddlewarePipeline — 按注册顺序执行中间件链

使用方式:
    pipeline = MiddlewarePipeline()
    pipeline.register(LoopDetectionMiddleware(window=5, redis_client=redis, run_id=run_id, callback=cb))
    pipeline.register(ObservabilityMiddleware(callback=callback))

    # 在 QueryEngine 的每轮循环中:
    ctx = TurnContext(turn_count=n, messages=messages, run_id=run_id)
    await pipeline.run_pre_turn(ctx)
    if ctx.abort:
        # 中断循环
    ... 正常执行 ...
    await pipeline.run_post_turn(ctx)

语义规则(ADR-025):
- run_pre_turn / run_pre_tool_use: 短路 — 某 mw 设 abort 后,后续 mw 不再执行
- run_post_tool_use / run_post_turn: 不短路 — 全部执行,即使某 mw 设 abort

进程边界: 本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.harness.middleware.base import Middleware, MiddlewareContext


class MiddlewarePipeline:
    """v4: 编排 4 钩点的中间件管道"""

    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def register(self, mw: Middleware) -> None:
        """注册中间件（按注册顺序执行）"""
        self._middlewares.append(mw)

    async def run_pre_turn(self, ctx: MiddlewareContext) -> None:
        """本轮 API 调用前钩点。短路：abort 后停止执行后续中间件。"""
        for mw in self._middlewares:
            await mw.pre_turn(ctx)
            if ctx.abort:
                return

    async def run_pre_tool_use(self, ctx: MiddlewareContext) -> None:
        """v4 新增: 工具执行前钩点。在 Hook 决策之前运行，可 abort 整个循环。短路。"""
        for mw in self._middlewares:
            await mw.pre_tool_use(ctx)
            if ctx.abort:
                return

    async def run_post_tool_use(self, ctx: MiddlewareContext) -> None:
        """v4 新增: 工具执行后钩点。可改写 tool_result。全部执行，不短路。"""
        for mw in self._middlewares:
            await mw.post_tool_use(ctx)

    async def run_post_turn(self, ctx: MiddlewareContext) -> None:
        """本轮结束后钩点。全部执行，不短路。"""
        for mw in self._middlewares:
            await mw.post_turn(ctx)
