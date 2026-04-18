"""executor/plugins — Skill 三级加载 + MCP Client + Plugin 扩展子包

DOC-05 Task 5.1: Skill 三级加载（ADR-043/044/045）
DOC-05 Task 5.2: MCP Server 双通道 + scope（ADR-046/047）
DOC-05 Task 5.3: Hook 治理 + Plugin 命名空间（ADR-048/049）
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
]
