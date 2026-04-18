"""
executor/agents/coordinator.py — Coordinator Agent（编排者）

Prism v2 专属 Agent：
- 只能调用 fork_agent / synthesize / task_stop 三种工具
- 不直接调用其他工具，通过 Fork 分派子任务
- max_turns=200，允许长时间编排复杂多步任务
- 进程边界不变：子 Agent 在独立子进程运行

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition

COORDINATOR_AGENT = AgentDefinition(
    agent_type="coordinator",
    description="编排 Agent，通过 Fork 子 Agent 分派子任务并综合结果",
    allowed_tools=["fork_agent", "synthesize", "task_stop"],
    max_turns=200,
    read_only=False,
    behavior_constraints=(
        "你是编排者，只能调用 fork_agent / synthesize / task_stop，不能直接调其他工具。\n"
        "你的职责是：\n"
        "1. 分析复杂任务，拆解为可并行或串行执行的子任务\n"
        "2. 通过 fork_agent 将子任务分派给合适类型的子 Agent 执行\n"
        "3. 等待子 Agent 完成后，通过 synthesize 综合子任务结果\n"
        "4. 全部完成后调用 task_stop 结束编排\n"
        "你不能直接读写文件、执行命令或调用外部服务——这些都必须通过 fork_agent 分派。\n"
        "子 Agent 执行时保持独立上下文隔离，你只能通过工具调用与它们交互。"
    ),
)
