"""
内置工具包

提供 register_builtin_tools() 函数，将所有内置工具注册到 ToolRegistry。
Task 3.1 仅注册 EchoTool；后续 Task 在此追加真实工具。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.tools.builtin.echo import EchoTool
from executor.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> None:
    """将所有内置工具注册到 ToolRegistry。

    MCP 工具优先级高于内置工具（同名时由 MCP 工具覆盖），
    因此本函数应在 MCP 工具注册之前调用。
    """
    registry.register(EchoTool())


__all__ = ["register_builtin_tools"]
