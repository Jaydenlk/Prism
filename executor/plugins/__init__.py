"""executor/plugins — Skill 三级加载 + MCP Client + Plugin 扩展子包

DOC-05 Task 5.1: Skill 三级加载（ADR-043/044/045）
DOC-05 Task 5.2: MCP Server 双通道 + scope（ADR-046/047）
DOC-05 Task 5.3: Hook 治理 + Plugin 命名空间（ADR-048/049）
DOC-05 Task 5.4: PluginHost 统一管理 + 变量替换系统（ADR-050）
"""

from executor.plugins.skill_types import SkillContent, SkillMetadata
from executor.plugins.skill_loader import SkillLoader
from executor.plugins.mcp_client import (
    MCPClient,
    MCPToolWrapper,
    filter_mcp_tools_for_agent,
    SCOPE_SYSTEM,
    SCOPE_USER,
)
from executor.plugins.namespace import PluginNamespace
from executor.plugins.plugin_types import PluginConfig, PluginScope
from executor.plugins.host import PluginHost, PluginVariableExpander, ENV_WHITELIST

__all__ = [
    # Task 5.1: Skill 三级加载
    "SkillContent",
    "SkillMetadata",
    "SkillLoader",
    # Task 5.2: MCP Client 双通道
    "MCPClient",
    "MCPToolWrapper",
    "filter_mcp_tools_for_agent",
    "SCOPE_SYSTEM",
    "SCOPE_USER",
    # Task 5.3: Plugin 命名空间
    "PluginNamespace",
    # Task 5.4: PluginHost 统一管理 + 变量替换
    "PluginConfig",
    "PluginScope",
    "PluginHost",
    "PluginVariableExpander",
    "ENV_WHITELIST",
]
