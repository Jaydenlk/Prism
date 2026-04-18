"""
反馈采集中间件

在 post_turn 阶段检查本轮是否有：
- 工具执行失败（is_error = True）
- 护栏拦截（permission_decision = deny）
- 循环检测命中

将失败事件结构化记录，通过 callback 上报 Backend。
这些数据是 Entropy Detection（DOC-12）和手动 Feedback Loop 的基础。

ADR-029: 结构化 feedback 事件 — event_type 5 枚举 + severity 4 枚举 + context dict + timestamp ISO 8601

进程边界: 本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

import structlog

from executor.harness.middleware.base import Middleware, MiddlewareContext

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()

# TTL 7 天（可通过环境变量覆盖）
FEEDBACK_TTL_SECONDS = int(os.environ.get("FEEDBACK_TTL_SECONDS", "604800"))

# 合法枚举值常量（供运行时显式校验）
VALID_EVENT_TYPES = frozenset({
    "tool_error",
    "permission_deny",
    "guardrail_hit",
    "loop_detected",
    "compaction_triggered",
})

VALID_SEVERITIES = frozenset({"info", "warning", "error", "critical"})


@dataclass
class FeedbackEvent:
    """v4 ADR-029: 结构化 feedback 事件"""

    event_type: Literal[
        "tool_error",
        "permission_deny",
        "guardrail_hit",
        "loop_detected",
        "compaction_triggered",
    ]
    severity: Literal["info", "warning", "error", "critical"]
    context: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class FeedbackCaptureMiddleware(Middleware):
    """反馈采集中间件（ADR-029）

    post_turn 阶段：
    1. 从 messages 尾部 3 条中提取 is_error=True 的 ToolResultBlock
    2. 从 ctx.custom_data["feedback_signals"] 提取其他中间件注入的信号
    3. 每条 FeedbackEvent 通过 callback 上报，并写入 Redis（TTL 7 天）
    4. Prometheus counter inc
    """

    name = "feedback_capture"

    def __init__(
        self,
        callback: "BackendCallback",
        redis_client=None,
    ) -> None:
        self._callback = callback
        self._redis = redis_client
        self._failures_this_run: list[FeedbackEvent] = []

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """扫描本轮结果，记录结构化失败事件"""
        events = self._extract_failures(ctx)
        for evt in events:
            self._failures_this_run.append(evt)
            await self._callback.harness_event("feedback_capture", asdict(evt))

            # Redis 缓存（TTL 7 天），供 Entropy Detector 扫描（DOC-12 Task 12.2）
            if self._redis is not None:
                key = f"feedback:{ctx.run_id}:{evt.timestamp}"
                try:
                    await self._redis.setex(
                        key,
                        FEEDBACK_TTL_SECONDS,
                        json.dumps(asdict(evt)),
                    )
                except Exception as e:
                    logger.warning(
                        "harness.feedback_capture.redis_error",
                        error=str(e),
                        key=key,
                    )

            # Prometheus counter
            try:
                from executor.observability.metrics import prism_harness_feedback_total

                prism_harness_feedback_total.labels(
                    event_type=evt.event_type,
                    severity=evt.severity,
                ).inc()
            except Exception:
                pass  # metrics 降级不影响主路径

    def _extract_failures(self, ctx: MiddlewareContext) -> list[FeedbackEvent]:
        """从 messages 尾部 + ctx.custom_data 提取失败事件"""
        events: list[FeedbackEvent] = []

        # 1. 最新 tool_result 是 is_error（检查尾部 3 条消息中 role=user 的第一条）
        for msg in reversed(ctx.messages[-3:]):
            if getattr(msg, "role", None) == "user":
                for block in getattr(msg, "content", []):
                    if getattr(block, "is_error", False):
                        events.append(
                            FeedbackEvent(
                                event_type="tool_error",
                                severity="error",
                                context={
                                    "run_id": ctx.run_id,
                                    "session_id": ctx.session_id,
                                    "tool_use_id": getattr(block, "tool_use_id", None),
                                    "preview": str(getattr(block, "content", ""))[:200],
                                },
                            )
                        )
                break  # 只处理尾部第一条 user 消息

        # 2. ctx.custom_data 中其他 Middleware 塞入的 guardrail/permission/loop 信号
        for sig in ctx.custom_data.get("feedback_signals", []):
            try:
                events.append(FeedbackEvent(**sig))
            except (TypeError, KeyError) as e:
                logger.warning(
                    "harness.feedback_capture.invalid_signal",
                    error=str(e),
                    signal=sig,
                )

        return events

    def get_run_summary(self) -> dict:
        """返回本次 Run 的失败摘要，写入 runs.harness_summary"""
        by_type: dict[str, int] = {}
        for evt in self._failures_this_run:
            by_type[evt.event_type] = by_type.get(evt.event_type, 0) + 1
        return {
            "total_failures": len(self._failures_this_run),
            "failure_types": by_type,
        }
