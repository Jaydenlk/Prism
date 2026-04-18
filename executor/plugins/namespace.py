"""
Plugin 命名空间管理（Task 5.3 ADR-049）

防止不同 Plugin 的 Skill / Hook / MCP 工具名称冲突。

命名约定：
- 无 Plugin 的资源：原始名称（如 "web_search"、"financial-analysis"）
- Plugin 内的资源："{plugin_name}:{resource_name}"（如 "finance:analysis"）
- MCP 工具：固定格式 "mcp__{server}__{tool}"（不受 Plugin 命名空间影响）

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations


class PluginNamespace:
    """Plugin 命名空间管理器。

    用法：
        ns = PluginNamespace("finance")
        qualified = ns.qualify("analysis")       # "finance:analysis"
        plugin, resource = ns.unqualify(qualified)  # ("finance", "analysis")

    无 Plugin（全局命名空间）时传入空字符串：
        ns = PluginNamespace("")
        ns.qualify("web_search")                 # "web_search"（原样返回）
    """

    def __init__(self, plugin_name: str = ""):
        self._plugin_name = plugin_name

    @property
    def plugin_name(self) -> str:
        """返回当前命名空间的 Plugin 名称（空字符串表示全局命名空间）。"""
        return self._plugin_name

    def qualify(self, resource_name: str) -> str:
        """为资源名称加上命名空间前缀。

        MCP 工具（mcp__ 开头）不加前缀，直接返回。
        无 Plugin 名称时原样返回。
        """
        if not self._plugin_name or self.is_mcp_tool(resource_name):
            return resource_name
        return f"{self._plugin_name}:{resource_name}"

    def unqualify(self, qualified_name: str) -> tuple[str, str]:
        """拆分命名空间前缀和资源名称。

        返回 (plugin_name, resource_name)：
        - "finance:analysis" → ("finance", "analysis")
        - "web_search" → ("", "web_search")
        - "mcp__search__web" → ("", "mcp__search__web")（MCP 工具不拆分）
        """
        if self.is_mcp_tool(qualified_name):
            return "", qualified_name
        if ":" in qualified_name:
            parts = qualified_name.split(":", 1)
            return parts[0], parts[1]
        return "", qualified_name

    @staticmethod
    def is_mcp_tool(name: str) -> bool:
        """判断名称是否为 MCP 工具（mcp__ 前缀）。"""
        return name.startswith("mcp__")

    @staticmethod
    def build_qualified(plugin_name: str, resource_name: str) -> str:
        """静态方法：直接构造命名空间限定名称。

        无 plugin_name 时原样返回 resource_name。
        """
        if not plugin_name:
            return resource_name
        return f"{plugin_name}:{resource_name}"
