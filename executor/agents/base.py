"""
executor/agents/base.py — Agent 定义基类(声明式 Agent 规格)

每种 Agent 声明：
- agent_type: 类型标识
- description: 用途说明
- allowed_tools: 工具白名单（None = 全部允许）
- denied_tools: 工具黑名单（优先于白名单）
- max_turns: 该类型 Agent 的循环上限（覆盖全局默认值）
- behavior_constraints: 注入到 Prompt 的行为约束文本
- output_format: 期望的输出格式说明（如 Planner 要求结构化 JSON）
- read_only: True 时 Harness 强制拦截所有写操作
- mcp_servers: ADR-030 MCP Server 白名单（None = 全部允许）
- frontmatter_skills: ADR-031 仅对此 agent_type 生效的 skill 列表
- bash_whitelist: Explore/Research 严格 Bash 命令白名单

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    """Agent 声明式定义(v4 扩展)"""

    agent_type: str
    description: str
    allowed_tools: list[str] | None = None      # None = 全部允许
    denied_tools: list[str] = field(default_factory=list)
    max_turns: int = 50                          # 可被全局配置覆盖
    behavior_constraints: str = ""               # 注入到 session_guidance_section
    output_format: str | None = None             # 期望输出格式
    read_only: bool = False                      # True 时 Harness 强制拦截所有写操作

    # v4 新增字段
    mcp_servers: list[str] | None = None         # ADR-030: MCP Server 白名单(None=全部)
    frontmatter_skills: list[str] = field(default_factory=list)  # ADR-031: 仅对此 agent_type 生效的 skill
    bash_whitelist: list[str] | None = None      # Explore/Research 严格 Bash 白名单

    def filter_tools(self, all_tools: list[str]) -> list[str]:
        """根据白名单/黑名单过滤可用工具。

        1. 若 allowed_tools 非 None，只保留白名单中的工具
        2. 然后移除 denied_tools 黑名单中的工具（黑名单优先）
        """
        if self.allowed_tools is not None:
            tools = [t for t in all_tools if t in self.allowed_tools]
        else:
            tools = list(all_tools)
        return [t for t in tools if t not in self.denied_tools]

    def filter_mcp_tools(self, all_mcp_tools: list[tuple[str, str]]) -> list[str]:
        """
        v4 ADR-030: 按 mcp_servers 白名单过滤 MCP 工具。

        all_mcp_tools: list of (mcp_server_name, tool_name)
        返回允许的 tool_name 列表。

        - mcp_servers is None: 返回所有 tool_name（无限制）
        - mcp_servers 非空列表: 只返回白名单 server 的工具
        """
        if self.mcp_servers is None:
            return [t for _, t in all_mcp_tools]
        return [t for srv, t in all_mcp_tools if srv in self.mcp_servers]
