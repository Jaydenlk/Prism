"""
内置工具包

提供 register_builtin_tools() 函数，将所有内置工具注册到 ToolRegistry。
Task 3.1 仅注册 EchoTool；Task 4.2 追加可选 ForkTool。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executor.tools.builtin.echo import EchoTool
from executor.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from executor.coordinator.fork_manager import ForkManager


def register_builtin_tools(
    registry: ToolRegistry,
    fork_manager: "ForkManager | None" = None,
) -> None:
    """将所有内置工具注册到 ToolRegistry。

    MCP 工具优先级高于内置工具（同名时由 MCP 工具覆盖），
    因此本函数应在 MCP 工具注册之前调用。

    Args:
        registry: 目标工具注册表。
        fork_manager: 若非 None，则注册 ForkTool（v4 Task 4.2）。
                      主 Agent 通过此工具主动派生子 Agent。
    """
    registry.register(EchoTool())
    if fork_manager is not None:
        from executor.tools.builtin.fork import ForkTool
        registry.register(ForkTool(fork_manager))


__all__ = ["register_builtin_tools"]
