"""
executor/agents/planner.py — Planner Agent（纯规划不执行）

对标 CC 的 Plan Agent：
- 只输出 step-by-step plan，不执行任何操作
- 只保留只读工具（用于理解当前状态）
- 输出格式为结构化计划，必须含 "Critical Files for Implementation" 清单
- max_turns=10，规划任务不需要太多轮

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition
from executor.agents.research import BASH_WHITELIST, READ_ONLY_TOOLS

PLANNER_AGENT = AgentDefinition(
    agent_type="planner",
    description="规划 Agent，分析任务并输出执行计划，不直接执行操作",
    allowed_tools=READ_ONLY_TOOLS,  # 复用 Explore 的只读工具集
    max_turns=10,                   # 规划不需要太多轮
    read_only=True,
    bash_whitelist=BASH_WHITELIST,
    behavior_constraints=(
        "你是规划者。\n"
        "你的工作是分析任务，理解当前状态，然后输出一个清晰的执行计划。\n"
        "绝对不要执行任何操作。只规划，不执行。\n"
        "你的输出必须是结构化的 step-by-step 计划。"
    ),
    output_format=(
        "输出格式要求（v4 强制）：\n"
        "1. 任务理解（一句话总结用户想要什么）\n"
        "2. 当前状态分析（基于你读取到的信息）\n"
        "3. 执行步骤（编号列表，每步包含：操作描述、需要的工具、预期结果、风险点）\n"
        "4. **Critical Files for Implementation**（v4 强制）：\n"
        "   列出实现该计划必须改动或新建的文件的绝对路径 + 用途。\n"
        "   这是验证阶段和 Coordinator 分派子任务的关键依据。\n"
        "5. 可逆性评估（每步是否可回滚，如何回滚）"
    ),
)
