"""
executor/agents/general.py — 通用 Agent

对标 CC 的 General Purpose Agent：
- 全部工具，无特殊限制
- 适用于大多数任务场景
- behavior_constraints 为空（依赖 PromptAssembler 通用行为规范）

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition

GENERAL_AGENT = AgentDefinition(
    agent_type="general",
    description="通用 Agent，拥有全部工具和能力，适用于大多数任务",
    allowed_tools=None,       # 全部允许
    max_turns=50,
    behavior_constraints="",  # 无额外约束，依赖 PromptAssembler 的通用行为规范
    read_only=False,
)
