"""
内置工具包

提供 register_builtin_tools() 函数，将所有内置工具注册到 ToolRegistry。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executor.tools.builtin.bash import BashTool
from executor.tools.builtin.echo import EchoTool
from executor.tools.builtin.edit import EditTool
from executor.tools.builtin.glob import GlobTool
from executor.tools.builtin.grep import GrepTool
from executor.tools.builtin.read import ReadTool
from executor.tools.builtin.skills_search import SkillsSearchTool
from executor.tools.builtin.web_fetch import WebFetchTool
from executor.tools.builtin.write import WriteTool
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

    Tool inventory (capability tag in []):
      - Echo            [—]              debug echo
      - Read            [read_file]      read file with line numbers
      - Write           [write_file]     overwrite/create file
      - Edit            [write_file]     find-replace edit
      - Glob            [read_file]      file pattern match
      - Grep            [read_file]      regex content search (rg + py fallback)
      - Bash            [exec_shell]     shell command with timeout
      - WebFetch        [web_access]     HTTP GET, html→text
      - SkillsSearch    [—]              search installed skills (read-only)
      - Fork            [fork_agent]     spawn sub-agent (only when fork_manager set)

    Per-agent capability filtering happens in the executor pipeline via
    AgentDefinition.allowed_capabilities; this function registers everything
    and lets the pipeline gate at execution time.
    """
    registry.register(EchoTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(BashTool())
    registry.register(WebFetchTool())
    registry.register(SkillsSearchTool(registry=skills_registry))
    if fork_manager is not None:
        from executor.tools.builtin.fork import ForkTool
        registry.register(ForkTool(fork_manager))


__all__ = [
    "register_builtin_tools",
    "BashTool",
    "EchoTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "ReadTool",
    "SkillsSearchTool",
    "WebFetchTool",
    "WriteTool",
]
