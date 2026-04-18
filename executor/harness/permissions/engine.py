"""
Permission Engine — 分层权限模型

两层权限检查：
Layer 1 — 平台级护栏（全局，不可覆盖）:
  - 由 GuardrailsEngine 提供的规则
  - 破坏性操作（rm -rf, DROP TABLE 等）直接 deny
  - 敏感数据操作直接 deny

Layer 2 — Hook 级权限（可配置）:
  - PreToolUse Hook 返回的 permission_decision
  - 支持 allow / deny / ask

ask 决策走 PermissionAskProtocol.ask()：Redis BLPOP 阻塞等待，超时 fail-safe deny（ADR-028）。

Prometheus metric：prism_permission_ask_total{decision} 计数。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from executor.harness.hooks.events import HookEvent
from executor.harness.permissions.result import PermissionResult

if TYPE_CHECKING:
    from executor.harness.guardrails.engine import GuardrailsEngine
    from executor.harness.hooks.system import HookSystem
    from executor.harness.permissions.ask_protocol import PermissionAskProtocol

logger = structlog.get_logger()


class PermissionEngine:
    """v4：两层权限模型，ask 走 Redis BLPOP 反向通信"""

    def __init__(
        self,
        guardrails: "GuardrailsEngine",
        hook_system: "HookSystem",
        ask_protocol: "PermissionAskProtocol",
    ) -> None:
        self._guardrails = guardrails
        self._hook_system = hook_system
        self._ask_protocol = ask_protocol

    async def check(
        self,
        tool_name: str,
        tool_input: dict,
        run_id: str,
        run_context=None,
    ) -> PermissionResult:
        """
        对工具调用做权限决策（v4 支持 ask 反向通信）。

        返回 PermissionResult：
        - decision: "allow" | "deny"
        - reason: str
        - updated_input: dict | None（Hook 可能改写了输入）
        """
        # Layer 1：平台级护栏（快速检查，ms 级）
        guardrail_result = self._guardrails.check(tool_name, tool_input, run_context)
        if guardrail_result.decision == "deny":
            logger.info(
                "harness.permission.guardrail_deny",
                tool_name=tool_name,
                reason=guardrail_result.reason,
            )
            return guardrail_result

        # Layer 2：Hook 级权限
        event = HookEvent(
            event_type="PreToolUse",
            tool_name=tool_name,
            tool_input=tool_input,
            run_id=run_id,
            session_id=getattr(run_context, "session_id", "") if run_context else "",
        )
        hook_decision = await self._hook_system.fire(event)

        if hook_decision.permission_decision == "deny":
            logger.info(
                "harness.permission.hook_deny",
                tool_name=tool_name,
                reason=hook_decision.reason,
            )
            return PermissionResult(
                decision="deny",
                reason=hook_decision.reason or "hook deny",
            )

        # v4 新增：ask 走反向通信（ADR-028，CLAUDE.md 陷阱 #8）
        if hook_decision.permission_decision == "ask":
            answer = await self._ask_protocol.ask(
                run_id=run_id,
                tool_name=tool_name,
                tool_input=tool_input,
                reason=hook_decision.reason or "需要用户确认",
            )
            # Prometheus metric
            try:
                from executor.observability.metrics import prism_permission_ask_total
                prism_permission_ask_total.labels(decision=answer).inc()
            except Exception:
                pass  # metrics 降级不影响主路径

            logger.info(
                "harness.permission.ask_answered",
                tool_name=tool_name,
                decision=answer,
            )
            if answer == "deny":
                return PermissionResult(decision="deny", reason="user denied")

        return PermissionResult(
            decision="allow",
            updated_input=hook_decision.updated_input,
        )
