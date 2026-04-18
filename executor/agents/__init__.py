"""
executor/agents/__init__.py — Agent 专业化系统公共导出（v4: 6 种 agent_type）

导出：
- AgentDefinition: 声明式 Agent 规格 dataclass
- AgentPool: Agent 工厂 + 注册表
- 6 种 AGENT 实例（含 EXPLORE_AGENT 别名）

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition
from executor.agents.coordinator import COORDINATOR_AGENT
from executor.agents.general import GENERAL_AGENT
from executor.agents.plugin_builder import PLUGIN_BUILDER_AGENT
from executor.agents.planner import PLANNER_AGENT
from executor.agents.pool import AgentPool
from executor.agents.research import (
    BASH_WHITELIST,
    EXPLORE_AGENT,
    READ_ONLY_TOOLS,
    RESEARCH_AGENT,
)
from executor.agents.verifier import VERIFIER_AGENT, VERIFIER_SYSTEM_PROMPT

__all__ = [
    # 基类
    "AgentDefinition",
    # 工厂
    "AgentPool",
    # 6 种 Agent 实例
    "GENERAL_AGENT",
    "RESEARCH_AGENT",
    "EXPLORE_AGENT",      # RESEARCH_AGENT 的别名
    "PLANNER_AGENT",
    "VERIFIER_AGENT",
    "COORDINATOR_AGENT",
    "PLUGIN_BUILDER_AGENT",
    # Verifier prompt（供外部引用）
    "VERIFIER_SYSTEM_PROMPT",
    # Research 常量（供 Harness 层引用）
    "READ_ONLY_TOOLS",
    "BASH_WHITELIST",
]
