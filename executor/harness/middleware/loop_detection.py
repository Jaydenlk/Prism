"""
循环检测中间件

检测 Agent 是否在重复调用同一工具+同一参数。
在 post_turn 阶段检查最近 N 轮的工具调用，如果发现
连续 N 次相同的 (tool_name, tool_input_hash)，触发告警。

状态通过 Redis 存储（key: harness:loop:{run_id}），支持跨 compaction 保持检测。

算法：
1. 从 ctx.messages 尾部提取本轮的 tool_use blocks
2. 对每个 tool_use block 生成指纹: sha256(tool_name + json.dumps(tool_input, sort_keys=True))
3. LPUSH 指纹到 Redis list，LTRIM 保留最近 window 条
4. LRANGE 获取全部列表，若全部相同且数量达到 window 条 → 循环命中
5. 命中后：ctx.abort = True，callback.harness_event("loop_detected")

进程边界: 本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import hashlib
import json

import structlog

from executor.callbacks.backend_callback import BackendCallback
from executor.harness.middleware.base import Middleware, MiddlewareContext

logger = structlog.get_logger()


class LoopDetectionMiddleware(Middleware):
    """循环检测中间件(ADR-025)

    构造器接受 window / redis_client / run_id / callback 四参数（显式传入，不从 QueryEngine 取）。
    """

    name: str = "loop_detection"

    def __init__(
        self,
        window: int,
        redis_client,
        run_id: str,
        callback: BackendCallback,
    ) -> None:
        self._window = window
        self._redis = redis_client
        self._run_id = run_id
        self._callback = callback
        self._redis_key = f"harness:loop:{run_id}"

    def _fingerprint(self, tool_name: str, tool_input: dict) -> str:
        """生成工具调用指纹: sha256(tool_name + json.dumps(tool_input, sort_keys=True))"""
        raw = tool_name + json.dumps(tool_input, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _extract_tool_use_from_messages(self, messages: list) -> list[tuple[str, dict]]:
        """从 messages 尾部提取最近一轮 assistant 的 tool_use blocks。

        返回 [(tool_name, tool_input), ...] 列表。
        """
        # 从后往前找最近一条 role="assistant" 的消息
        for msg in reversed(messages):
            role = getattr(msg, "role", None) or (
                msg.get("role") if isinstance(msg, dict) else None
            )
            if role == "assistant":
                content = getattr(msg, "content", None) or (
                    msg.get("content") if isinstance(msg, dict) else []
                )
                if not content:
                    return []
                results = []
                for block in content:
                    # 支持 dataclass 和 dict 两种形式
                    block_type = getattr(block, "type", None) or (
                        block.get("type") if isinstance(block, dict) else None
                    )
                    if block_type == "tool_use":
                        name = getattr(block, "name", None) or (
                            block.get("name") if isinstance(block, dict) else ""
                        )
                        inp = getattr(block, "input", None) or (
                            block.get("input") if isinstance(block, dict) else {}
                        )
                        results.append((name or "", inp or {}))
                return results
        return []

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """检查最近 messages 中的工具调用是否有循环模式"""
        tool_calls = self._extract_tool_use_from_messages(ctx.messages)
        if not tool_calls:
            return

        # 为本轮所有工具调用生成一个合并指纹（代表本轮工具调用模式）
        turn_fingerprint = "|".join(
            self._fingerprint(name, inp) for name, inp in tool_calls
        )

        # LPUSH 最新指纹，LTRIM 保留最近 window 条
        pipe = self._redis.pipeline()
        pipe.lpush(self._redis_key, turn_fingerprint)
        pipe.ltrim(self._redis_key, 0, self._window - 1)
        await pipe.execute()

        # 读取当前列表
        recent: list[str] = await self._redis.lrange(self._redis_key, 0, -1)

        # 判断：需满足 window 条且全部相同
        if len(recent) < self._window:
            return

        if len(set(recent)) == 1:
            logger.warning(
                "harness.loop_detection.loop_detected",
                run_id=self._run_id,
                turn_count=ctx.turn_count,
                window=self._window,
                fingerprint=recent[0],
            )
            ctx.abort = True
            ctx.abort_reason = f"循环检测命中：最近 {self._window} 轮工具调用完全相同"
            await self._callback.harness_event(
                "loop_detected",
                {
                    "run_id": self._run_id,
                    "turn_count": ctx.turn_count,
                    "window": self._window,
                    "fingerprint": recent[0],
                    "abort_reason": ctx.abort_reason,
                },
            )
