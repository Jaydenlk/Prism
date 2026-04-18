"""
SkillsSearchTool — Agent 内置只读搜索工具

DOC-05 Task 5.6: Skills CLI & Agent Tool（ADR-052）
ADR-052 (PRD 原标 ADR-048 平移): Agent 只允许搜索 Skill 市场，不允许安装/卸载/更新。
  - 安装行为涉及下载 + 执行第三方代码 + 注册 hook，风险太高
  - 安装走 UI/CLI 人工流程（Skills Store 页面，DOC-11 v4 Task 11.5）
  - 搜索无副作用，可以给 Agent 自由搜索以供用户决策

来源: Master M8; PRD DOC-05 v4 Task 5.6 Part A

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import json

import structlog

from executor.plugins.skills_registry import LocalSource, SkillPackage, SkillsRegistry
from executor.tools.base import BaseTool, ToolResult

logger = structlog.get_logger()


class SkillsSearchTool(BaseTool):
    """Agent 内置只读 Skill 搜索工具（ADR-052）

    v4：只允许 Agent 搜索 Skill 市场（Local + GitHub 两源），供用户决策参考。
    不允许安装。安装操作仍需用户在 UI 手动触发，或通过 CLI 执行。

    capabilities: [] — 无特殊 capability 要求（搜索是只读操作）
    """

    # v4 只读操作，无 capability 限制
    capabilities: list[str] = []

    @property
    def name(self) -> str:
        return "skills_search"

    @property
    def description(self) -> str:
        return (
            "搜索 Prism Skills 市场（Local + GitHub 两源），返回候选 Skill 列表"
            "供用户参考。你不能直接安装 Skill，需要告诉用户点击 UI 的 Skills Store 页面"
            "手动安装，或者通过 'prism skills install <package_id>' CLI 命令安装。"
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（支持 name/description/tags 模糊匹配，空字符串返回全部）",
                },
                "source": {
                    "type": "string",
                    "enum": ["local", "github"],
                    "description": "指定源（可选，默认全部源）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果最大数量（默认 20，最大 50）",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        }

    def __init__(self, registry: SkillsRegistry | None = None) -> None:
        """
        Args:
            registry: SkillsRegistry 实例（可选）。
                      若为 None，运行时创建仅含 LocalSource 的默认注册表。
                      GitHub 源需要注入含 GITHUB_TOKEN 的 GitHubSource 实例。
        """
        self._registry = registry

    async def execute(self, tool_input: dict) -> ToolResult:
        """搜索 Skill 市场，返回 JSON 格式结果。

        v4 约束：
        - 仅搜索，不安装
        - 返回结果包含 name/description/version/source/source_url/installed/tags
        - 结果条数上限 50
        """
        query: str = tool_input.get("query", "")
        source_filter: str | None = tool_input.get("source")
        limit: int = min(int(tool_input.get("limit", 20)), 50)

        registry = self._get_registry()

        sources: list[str] | None = [source_filter] if source_filter else None

        try:
            packages = await registry.search(query, sources=sources)
        except Exception as exc:
            logger.warning(
                "skills_search_tool.search_error",
                query=query,
                error=str(exc),
            )
            return ToolResult(
                content=json.dumps(
                    {
                        "error": f"搜索失败: {exc}",
                        "results": [],
                        "total": 0,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
            )

        # 截断结果
        truncated = packages[:limit]
        results = [self._package_to_dict(p) for p in truncated]

        logger.info(
            "skills_search_tool.execute",
            query=query,
            source_filter=source_filter,
            found=len(packages),
            returned=len(results),
        )

        return ToolResult(
            content=json.dumps(
                {
                    "query": query,
                    "source_filter": source_filter,
                    "total": len(packages),
                    "returned": len(results),
                    "results": results,
                    "note": (
                        "如需安装 Skill，请通过 UI 的 Skills Store 页面或"
                        " 'prism skills install <package_id> --source <local|github>' CLI 命令操作。"
                        " Agent 无法直接安装 Skill（ADR-052 安全约束）。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_registry(self) -> SkillsRegistry:
        """获取 SkillsRegistry 实例（懒加载默认注册表）。"""
        if self._registry is not None:
            return self._registry

        import os

        # 默认只含 LocalSource（无 GITHUB_TOKEN 则 GitHubSource 返回空列表）
        workspace = os.getcwd()
        install_dir = os.path.join(workspace, ".prism", "skills")
        local_source = LocalSource(workspace=workspace)

        try:
            from executor.plugins.skills_registry import GitHubSource
            github_source = GitHubSource()  # 无 token 时 search 返回空列表
            sources = [local_source, github_source]
        except Exception:
            sources = [local_source]

        return SkillsRegistry(sources=sources, install_dir=install_dir)

    @staticmethod
    def _package_to_dict(pkg: SkillPackage) -> dict:
        """将 SkillPackage 转换为可序列化 dict。"""
        return {
            "name": pkg.name,
            "description": pkg.description,
            "version": pkg.version,
            "source": pkg.source,
            "source_url": pkg.source_url,
            "author": pkg.author,
            "tags": pkg.tags,
            "installed": pkg.installed,
            "installed_version": pkg.installed_version,
        }
