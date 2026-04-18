"""
工具执行 Pipeline

完整链路（对标 CC 的 Tool.ts + runTools()）：
1. 从 ToolRegistry 查找工具
2. JSON Schema 校验 input
3. PermissionEngine 决策点（PreToolUse Hook + Guardrails）
4. updated_input 改写（Hook 可能改写工具输入）
5. 执行 tool.execute()
6. ContextBudgetManager.truncate_tool_result() 截断超长结果
7. PostToolUse Hook 拦截点（检查输出，可改写 MCP 输出）
8. 返回 ToolResultBlock

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jsonschema
import structlog

from executor.adapters.base import ToolResultBlock
from executor.engine.context_budget import ContextBudgetManager
from executor.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from executor.harness.hooks.system import HookSystem
    from executor.harness.permissions.engine import PermissionEngine

logger = structlog.get_logger()


class ToolExecutionPipeline:
    """工具执行 Pipeline（7 步链路）"""

    def __init__(
        self,
        registry: ToolRegistry,
        context_budget: ContextBudgetManager,
        permission_engine: "PermissionEngine | None" = None,
        hook_system: "HookSystem | None" = None,
    ) -> None:
        self._registry = registry
        self._budget = context_budget
        self._permission_engine = permission_engine
        self._hook_system = hook_system

    async def execute(
        self,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        run_context: object | None = None,
    ) -> ToolResultBlock:
        """
        执行单个工具调用。
        返回 ToolResultBlock（直接追加到 messages）。
        """
        # 1. 查找工具
        tool = self._registry.get(tool_name)
        if tool is None:
            logger.warning(
                "harness.tool.not_found",
                tool_name=tool_name,
                tool_use_id=tool_use_id,
            )
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"工具 '{tool_name}' 不存在",
                is_error=True,
            )

        # 2. JSON Schema 校验
        try:
            jsonschema.validate(instance=tool_input, schema=tool.input_schema)
        except jsonschema.ValidationError as e:
            logger.warning(
                "harness.tool.schema_validation_failed",
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                error=e.message,
            )
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"参数校验失败: {e.message}",
                is_error=True,
            )

        # 3. PermissionEngine 决策（PreToolUse Hook + Guardrails，Task 3.3）
        if self._permission_engine is not None:
            run_id = getattr(run_context, "run_id", "") if run_context else ""
            permission_result = await self._permission_engine.check(
                tool_name=tool_name,
                tool_input=tool_input,
                run_id=run_id,
                run_context=run_context,
            )
            if permission_result.decision == "deny":
                logger.info(
                    "harness.tool.permission_denied",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    reason=permission_result.reason,
                )
                return ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=f"权限拒绝: {permission_result.reason}",
                    is_error=True,
                )
            # 4. updated_input 改写（Hook 可能改写工具输入）
            if permission_result.updated_input is not None:
                logger.info(
                    "harness.tool.input_rewritten",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                )
                tool_input = permission_result.updated_input

        # 5. 执行
        try:
            result = await tool.execute(tool_input)
        except Exception as e:
            logger.error(
                "harness.tool.execute_error",
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                error=str(e),
            )
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"工具执行异常: {str(e)}",
                is_error=True,
            )

        # 6. 截断超长结果
        truncated_content = self._budget.truncate_tool_result(result.content)

        # 7. PostToolUse Hook（Task 3.3：检查输出，可改写 MCP 输出）
        if self._hook_system is not None:
            from executor.harness.hooks.events import HookEvent
            post_event = HookEvent(
                event_type="PostToolUse",
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=truncated_content,
                is_error=result.is_error,
                run_id=getattr(run_context, "run_id", "") if run_context else "",
                session_id=getattr(run_context, "session_id", "") if run_context else "",
            )
            post_decision = await self._hook_system.fire(post_event)
            # updated_mcp_tool_output 若非 None 则 override
            if post_decision.updated_mcp_tool_output is not None:
                import json as _json
                truncated_content = _json.dumps(
                    post_decision.updated_mcp_tool_output, ensure_ascii=False
                )
            # prevent_continuation / additional_context / blocking_error — 本 Task 只 log
            if post_decision.prevent_continuation:
                logger.info(
                    "harness.tool.post_hook_prevent_continuation",
                    tool_name=tool_name,
                )
            if post_decision.additional_context:
                logger.info(
                    "harness.tool.post_hook_additional_context",
                    tool_name=tool_name,
                    context=post_decision.additional_context[:200],
                )
            if post_decision.blocking_error:
                logger.warning(
                    "harness.tool.post_hook_blocking_error",
                    tool_name=tool_name,
                    error=post_decision.blocking_error[:200],
                )

        # 8. 返回
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=truncated_content,
            is_error=result.is_error,
        )
