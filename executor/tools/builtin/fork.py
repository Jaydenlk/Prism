"""
Fork 工具 — 允许 Agent 主动发起子 Agent

模型可以通过调用此工具来 fork 一个专业化子 Agent。
这是 Agent 自主编排的关键——模型决定何时需要 fork，Runtime 执行。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executor.coordinator.fork_briefing import ForkBriefing
from executor.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from executor.coordinator.fork_manager import ForkManager


class ForkTool(BaseTool):
    """Fork 工具：派生专业化子 Agent 执行隔离子任务（v4 ADR-033/034/035）"""

    capabilities: list[str] = ["fork_agent"]

    def __init__(self, fork_manager: "ForkManager"):
        self._fork_manager = fork_manager

    @property
    def name(self) -> str:
        return "fork_agent"

    @property
    def description(self) -> str:
        return (
            "派生一个专业化子 Agent 来执行特定子任务。"
            "子 Agent 在隔离的上下文中运行，完成后将结论返回给你。"
            "可用的 Agent 类型: research（只读调研）, planner（制定计划）, verifier（验证结果）。"
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "enum": ["research", "planner", "verifier"],
                    "description": "子 Agent 类型",
                },
                "goal": {
                    "type": "string",
                    "description": "交给子 Agent 的目标（一句话概括）",
                },
                "why": {
                    "type": "string",
                    "description": "发起 Fork 的动机，帮助子 Agent 理解决策上下文",
                },
                "excluded": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "明确排除的做法列表",
                },
                "context": {
                    "type": "string",
                    "description": "已知背景信息，避免子 Agent 重复调研",
                },
                "expected_output": {
                    "type": "string",
                    "description": "期望的 synthesis 格式或内容要求",
                },
                "file_references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "子 Agent 需要关注的文件路径列表",
                },
            },
            "required": ["agent_type", "goal"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        """构造 ForkBriefing 并调用 ForkManager.fork()，返回 synthesis 结论"""
        briefing = ForkBriefing(
            goal=tool_input["goal"],
            why=tool_input.get("why", ""),
            excluded=tool_input.get("excluded", []),
            context=tool_input.get("context", ""),
            expected_output=tool_input.get("expected_output", ""),
            file_references=tool_input.get("file_references", []),
        )

        result = await self._fork_manager.fork(
            agent_type=tool_input["agent_type"],
            briefing=briefing,
        )

        if result.success:
            return ToolResult(
                content=(
                    f"[{result.agent_type} Agent 完成，{result.turn_count} 轮，"
                    f"{result.input_tokens + result.output_tokens} tokens]\n\n"
                    f"{result.synthesis}"
                ),
            )
        else:
            return ToolResult(
                content=f"子 Agent 执行失败: {result.error}",
                is_error=True,
            )
