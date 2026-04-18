"""
executor/agents/pool.py — AgentPool（Agent 工厂 + 注册表）

职责：
- 注册所有 Agent 定义（v4: 6 种）
- 按类型返回 AgentDefinition（不存在则回退 general）
- 向后兼容别名：chat→general, research→explore, build→general
- 根据 AgentDefinition 过滤 ToolRegistry 中的工具

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executor.agents.base import AgentDefinition
from executor.agents.coordinator import COORDINATOR_AGENT
from executor.agents.general import GENERAL_AGENT
from executor.agents.plugin_builder import PLUGIN_BUILDER_AGENT
from executor.agents.planner import PLANNER_AGENT
from executor.agents.research import EXPLORE_AGENT, RESEARCH_AGENT
from executor.agents.verifier import VERIFIER_AGENT

if TYPE_CHECKING:
    from executor.tools.registry import ToolRegistry
    from executor.tools.base import ToolDefinition


class AgentPool:
    """Agent 工厂 + 注册表（v4: 6 种 agent_type）"""

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}

        # v4: 注册 6 种 Agent（按正式 agent_type 键注册）
        for agent_def in [
            GENERAL_AGENT,        # general
            EXPLORE_AGENT,        # explore
            PLANNER_AGENT,        # planner
            VERIFIER_AGENT,       # verifier
            COORDINATOR_AGENT,    # coordinator
            PLUGIN_BUILDER_AGENT, # plugin_builder
        ]:
            self._definitions[agent_def.agent_type] = agent_def

        # 向后兼容别名（chat/research/build → 正式 agent_type 实例）
        self._definitions["chat"] = GENERAL_AGENT     # DEFAULT_AGENT_CONSTRAINTS 含 "chat" 键
        self._definitions["research"] = EXPLORE_AGENT  # 旧版 research 别名
        self._definitions["build"] = GENERAL_AGENT     # 旧版 build 别名

    def get(self, agent_type: str) -> AgentDefinition:
        """获取 Agent 定义。不存在则回退到 general。

        别名映射（含向后兼容）:
        - "chat"     → GENERAL_AGENT（agent_type="general"）
        - "research" → EXPLORE_AGENT（agent_type="explore"）
        - "build"    → GENERAL_AGENT（agent_type="general"）
        - 未知类型  → GENERAL_AGENT（fallback）
        """
        return self._definitions.get(agent_type, GENERAL_AGENT)

    def list_types(self) -> list[str]:
        """返回所有注册的 agent_type 键（含别名）。"""
        return list(self._definitions.keys())

    def filter_tools_for_agent(
        self,
        agent_type: str,
        registry: "ToolRegistry",
    ) -> list["ToolDefinition"]:
        """
        根据 Agent 类型过滤可用工具，返回排序后的 ToolDefinition 列表。

        使用 AgentDefinition.filter_tools() 做白名单/黑名单过滤。
        """
        agent_def = self.get(agent_type)
        all_tool_names = [t.name for t in registry.list_definitions()]
        allowed_names = agent_def.filter_tools(all_tool_names)
        return sorted(
            [d for d in registry.list_definitions() if d.name in allowed_names],
            key=lambda d: d.name,
        )
