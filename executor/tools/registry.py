"""
工具注册表

职责：
- 注册内置工具和 MCP 工具
- 按名称查找工具实例
- 返回所有工具的 ToolDefinition 列表（供 PromptAssembler 使用）

进程边界：本模块只 import executor.tools.base 和 executor.adapters.base，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.adapters.base import ToolDefinition
from executor.tools.base import BaseTool


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。名称重复则覆盖（MCP 工具可覆盖内置同名工具）。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称查找工具实例。不存在返回 None。"""
        return self._tools.get(name)

    def list_definitions(self) -> list[ToolDefinition]:
        """返回所有工具的 ToolDefinition，按名称排序（cache 友好）"""
        return sorted(
            [t.to_definition() for t in self._tools.values()],
            key=lambda d: d.name,
        )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
