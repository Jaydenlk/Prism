"""
内置工具包

提供 register_builtin_tools() 函数，将所有内置工具注册到 ToolRegistry。
Task 3.1 仅注册 EchoTool；Task 4.2 追加可选 ForkTool；Task 5.6 追加 SkillsSearchTool。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executor.tools.builtin.echo import EchoTool
from executor.tools.builtin.skills_search import SkillsSearchTool
from executor.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from executor.coordinator.fork_manager import ForkManager
    from executor.plugins.skills_registry import SkillsRegistry


def register_builtin_tools(
    registry: ToolRegistry,
    fork_manager: "ForkManager | None" = None,
    skills_registry: "SkillsRegistry | None" = None,
) -> None:
    """将所有内置工具注册到 ToolRegistry。

    MCP 工具优先级高于内置工具（同名时由 MCP 工具覆盖），
    因此本函数应在 MCP 工具注册之前调用。

    Args:
        registry: 目标工具注册表。
        fork_manager: 若非 None，则注册 ForkTool（v4 Task 4.2）。
                      主 Agent 通过此工具主动派生子 Agent。
        skills_registry: 若非 None，则注入到 SkillsSearchTool（v4 Task 5.6，ADR-052）。
                         为 None 时 SkillsSearchTool 懒加载默认注册表（含 LocalSource）。
    """
    registry.register(EchoTool())
    # v4 Task 5.6 ADR-052: Agent 只读搜索工具（无 install/uninstall 权限）
    registry.register(SkillsSearchTool(registry=skills_registry))
    if fork_manager is not None:
        from executor.tools.builtin.fork import ForkTool
        registry.register(ForkTool(fork_manager))


__all__ = ["register_builtin_tools", "SkillsSearchTool"]
