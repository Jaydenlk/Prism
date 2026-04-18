"""
工具执行 Pipeline

完整链路（对标 CC 的 Tool.ts + runTools()）：
1. 从 ToolRegistry 查找工具
2. JSON Schema 校验 input
3. [预留] PreToolUse Hook 拦截点（Task 3.3 实现）
4. [预留] PermissionEngine 决策点（Task 3.3 实现）
5. 执行 tool.execute()
6. ContextBudgetManager.truncate_tool_result() 截断超长结果
7. [预留] PostToolUse Hook 拦截点（Task 3.3 实现）
8. 返回 ToolResultBlock

本 Task 先实现 1-2-5-6-8 的骨架链路，Hook 和 Permission 的集成点用
明确的注释标记（# HARNESS_INTEGRATION_POINT），Task 3.3 填充。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import jsonschema
import structlog

from executor.adapters.base import ToolResultBlock
from executor.engine.context_budget import ContextBudgetManager
from executor.tools.registry import ToolRegistry

logger = structlog.get_logger()


class ToolExecutionPipeline:
    """工具执行 Pipeline（7 步链路）"""

    def __init__(
        self,
        registry: ToolRegistry,
        context_budget: ContextBudgetManager,
    ) -> None:
        self._registry = registry
        self._budget = context_budget
        # HARNESS_INTEGRATION_POINT: hook_system 和 permission_engine 在 Task 3.3 注入
        self._hook_system = None
        self._permission_engine = None

    async def execute(
        self,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        run_context: object | None = None,  # v4：预留给 Task 3.3 Hook/Permission 使用
    ) -> ToolResultBlock:
        """
        执行单个工具调用。
        返回 ToolResultBlock（直接追加到 messages）。

        run_context 当前 Task 3.1 内部不使用，Task 3.3 的 Hook / Permission 会用。
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

        # 3. HARNESS_INTEGRATION_POINT: PreToolUse Hook（Task 3.3 实现）
        # hook_decision = await self._hook_system.pre_tool_use(tool_name, tool_input, run_context)
        # if hook_decision.block: return ToolResultBlock(tool_use_id=tool_use_id, content=hook_decision.reason, is_error=True)

        # 4. HARNESS_INTEGRATION_POINT: PermissionEngine.check()（Task 3.3 实现）
        # decision = await self._permission_engine.check(tool_name, tool_input, run_context)
        # if decision == "deny": return ToolResultBlock(tool_use_id=tool_use_id, content="权限拒绝", is_error=True)
        # if decision == "ask": answer = await PermissionAskProtocol.ask(run_context, tool_name, tool_input)

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

        # 7. HARNESS_INTEGRATION_POINT: PostToolUse Hook（Task 3.3 实现）
        # await self._hook_system.post_tool_use(tool_name, tool_input, truncated_content, run_context)

        # 8. 返回
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=truncated_content,
            is_error=result.is_error,
        )
