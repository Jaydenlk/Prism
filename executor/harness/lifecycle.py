"""
Harness 生命周期控制器（v4 Task 3.4）

职责：一站式组装所有 Harness 子系统，返回给 __main__.py 使用。

初始化顺序：
1. GuardrailsEngine（平台级规则加载）
2. HookSystem（从配置文件加载 Hook）
3. PermissionAskProtocol（Redis BLPOP 反向通信，ADR-028）
4. PermissionEngine（组合 Guardrails + HookSystem + AskProtocol）
5. FeedbackCaptureMiddleware（ADR-029 结构化事件）
6. LoopDetectionMiddleware（ADR-025）
7. ObservabilityMiddleware
8. MiddlewarePipeline（注册顺序：loop → observability → feedback）

SessionEnd Hook 触发 user_memory 提炼（ADR-030）：
- turns > 5 时 LLM 凝练本 session 要点 → callback.harness_event("user_memory_extracted")

进程边界：本模块只 import executor.*，禁止 import backend.app.*

__HarnessLifecycle 向后兼容别名保留（Task 3.3 已用此名的引用不受影响）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from executor.harness.guardrails.engine import GuardrailsEngine
from executor.harness.hooks.events import HookEvent
from executor.harness.hooks.system import HookSystem
from executor.harness.middleware.feedback_capture import FeedbackCaptureMiddleware
from executor.harness.middleware.loop_detection import LoopDetectionMiddleware
from executor.harness.middleware.observability import ObservabilityMiddleware
from executor.harness.middleware.pipeline import MiddlewarePipeline
from executor.harness.permissions.ask_protocol import PermissionAskProtocol
from executor.harness.permissions.engine import PermissionEngine

if TYPE_CHECKING:
    from executor.adapters.base import PrismMessage
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()


def _extract_text(msg) -> str:
    """从 PrismMessage content 提取首个 text 块"""
    for block in getattr(msg, "content", []):
        if hasattr(block, "text"):
            return block.text
    return ""


class HarnessRuntime:
    """Harness 运行时控制器 — 一站式组装所有治理子系统（v4 Task 3.4）"""

    def __init__(
        self,
        run_id: str,
        session_id: str,
        user_id: str,
        callback: "BackendCallback",
        redis_client,
        redis_url: str,
        adapter,
        settings,
    ) -> None:
        self.run_id = run_id
        self.session_id = session_id
        self.user_id = user_id
        self._callback = callback
        self._adapter = adapter

        # 1. GuardrailsEngine（自动加载 4 条平台规则）
        self.guardrails = GuardrailsEngine()

        # 2. HookSystem（加载 .prism/hooks.json，不存在时静默跳过）
        self.hook_system = HookSystem()
        self.hook_system.load_from_config(".prism/hooks.json")

        # 3. PermissionAskProtocol（Redis BLPOP 反向通信，ADR-028）
        self.ask_protocol = PermissionAskProtocol(
            redis_url=redis_url,
            callback=callback,
        )

        # 4. PermissionEngine（两层：Guardrails + HookSystem + AskProtocol）
        self.permission_engine = PermissionEngine(
            guardrails=self.guardrails,
            hook_system=self.hook_system,
            ask_protocol=self.ask_protocol,
        )

        # 5. FeedbackCaptureMiddleware（ADR-029）
        self.feedback_mw = FeedbackCaptureMiddleware(
            callback,
            redis_client=redis_client,
        )

        # 6. LoopDetectionMiddleware（ADR-025）
        self.loop_mw = LoopDetectionMiddleware(
            window=settings.LOOP_DETECTION_WINDOW,
            redis_client=redis_client,
            run_id=run_id,
            callback=callback,
        )

        # 7. ObservabilityMiddleware
        self.observability_mw = ObservabilityMiddleware(callback)

        # 8. MiddlewarePipeline（注册顺序：loop → observability → feedback）
        self.middleware = MiddlewarePipeline()
        self.middleware.register(self.loop_mw)
        self.middleware.register(self.observability_mw)
        self.middleware.register(self.feedback_mw)

        logger.info(
            "harness.runtime.initialized",
            run_id=run_id,
            session_id=session_id,
            middleware_count=len(self.middleware._middlewares),
            guardrail_rules=len(self.guardrails._rules),
        )

    def inject_into_pipeline(self, pipeline) -> None:
        """将 Harness 子系统注入到 ToolExecutionPipeline（ADR-020）"""
        pipeline._permission_engine = self.permission_engine
        pipeline._hook_system = self.hook_system

    async def on_session_start(self) -> None:
        """触发 SessionStart Hook"""
        await self.hook_system.fire(
            HookEvent(
                event_type="SessionStart",
                run_id=self.run_id,
                session_id=self.session_id,
            )
        )

    async def on_session_end(self, messages: list, turn_count: int) -> None:
        """
        v4 ADR-030: SessionEnd Hook + user_memory 提炼

        1. fire SessionEnd hook
        2. 若 turn_count > 5：LLM 凝练本 session 要点 → callback 上报
        异常 log WARNING，不 raise（不影响主循环）
        """
        await self.hook_system.fire(
            HookEvent(
                event_type="SessionEnd",
                run_id=self.run_id,
                session_id=self.session_id,
            )
        )

        # turns <= 5 短会话无价值，跳过提炼
        if turn_count <= 5:
            return

        # 拼接 user/assistant 消息历史，截断 12000 字符（保守裁剪，避免提炼 prompt 超长）
        history_text = "\n\n".join(
            f"{m.role}: {_extract_text(m)}"
            for m in messages
            if getattr(m, "role", None) in ("user", "assistant")
        )[:12000]

        prompt = (
            "请从以下对话中凝练出对下次会话有价值的要点，以要点列表输出，"
            "≤200 字。重点抓：1) 用户明确偏好/禁令；2) 达成的关键决策；"
            "3) 未完成的事项。不要复述对话。\n\n" + history_text
        )

        try:
            from executor.adapters.base import PrismMessage, TextBlock

            resp = await self._adapter.complete(
                messages=[
                    PrismMessage(role="user", content=[TextBlock(text=prompt)])
                ],
                system_prompt="你是要点提炼工具。只输出要点列表，不说其他。",
                max_tokens=400,
            )
            content = resp.messages[0].content[0].text.strip()
            if content:
                await self._callback.harness_event(
                    "user_memory_extracted",
                    {
                        "content": content,
                        "source_session_id": self.session_id,
                        "source_run_id": self.run_id,
                    },
                )
                try:
                    from executor.observability.metrics import (
                        prism_harness_memory_extracted_total,
                    )

                    prism_harness_memory_extracted_total.inc()
                except Exception:
                    pass  # metrics 降级不影响主路径
        except Exception as e:
            logger.warning("harness.memory.extract_failed", error=str(e))

    def get_run_harness_summary(self) -> dict:
        """返回完整的 Harness 运行摘要（写入 runs.harness_summary）"""
        return {
            **self.feedback_mw.get_run_summary(),
            "middleware_count": len(self.middleware._middlewares),
            "guardrail_rules_count": len(self.guardrails._rules),
        }

    async def close(self) -> None:
        """释放资源（Redis 连接等）"""
        await self.ask_protocol.close()
        logger.info("harness.runtime.closed", run_id=self.run_id)


# 向后兼容别名（Task 3.3 代码引用 HarnessLifecycle 不受影响）
HarnessLifecycle = HarnessRuntime
