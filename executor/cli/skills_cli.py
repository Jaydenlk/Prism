"""
Skills CLI — Prism Skills 命令行管理工具

DOC-05 Task 5.6: Skills CLI & Agent Tool（ADR-053）
ADR-053 (PRD 原标 ADR-049 平移): Backend 统一处理安装行为，写 skill_installs 表。
  CLI 在容器内直接调用 SkillsRegistry（executor 侧），再通过 Backend API 更新 DB。
  CLI 不直接操作 DB，走 Backend REST API（install/uninstall → POST /skills/install）。

命令列表:
  prism skills search <query> [--source local|github] [--limit N]
  prism skills install <package_id> --source <local|github> [--version <ver>]
  prism skills uninstall <skill_name>
  prism skills update <skill_name>
  prism skills list [--source <source>]
  prism skills info <skill_name>

用法:
  python -m executor.cli.skills_cli <command> [args...]
  或容器内: prism skills <command> [args...]

来源: PRD DOC-05 v4 Task 5.6 Part A

进程边界：本模块只 import executor.* + stdlib，禁止 import backend.app.*
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import structlog

from executor.plugins.skills_registry import (
    GitHubSource,
    InstalledSkill,
    LocalSource,
    SkillPackage,
    SkillsRegistry,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 默认路径配置
# ---------------------------------------------------------------------------

_DEFAULT_WORKSPACE = os.getcwd()
_DEFAULT_INSTALL_DIR = os.path.join(_DEFAULT_WORKSPACE, ".prism", "skills")


# ---------------------------------------------------------------------------
# SkillsCLI — 主类
# ---------------------------------------------------------------------------


class SkillsCLI:
    """Prism Skills 命令行工具（ADR-053）

    子命令：search / install / uninstall / update / list / info

    v4 设计原则：
    - CLI 和 UI 都走 Backend REST API 完成 install/uninstall（写 DB）
    - CLI 模式：无 backend_url 时，直接操作 SkillsRegistry（开发者模式）
    - 安装后输出提示用户通过 Backend API 同步 DB
    """

    def __init__(
        self,
        workspace: str = _DEFAULT_WORKSPACE,
        github_token: str | None = None,
        backend_url: str | None = None,
    ) -> None:
        """
        Args:
            workspace: 工作目录根路径（默认 CWD）
            github_token: GitHub Personal Access Token（可选，优先级高于环境变量）
            backend_url: Backend REST API base URL（如 http://localhost:8000）
                         若提供，install/uninstall 走 API；否则直接操作文件系统。
        """
        self._workspace = workspace
        self._backend_url = backend_url

        install_dir = os.path.join(workspace, ".prism", "skills")
        local_source = LocalSource(workspace=workspace)
        github_source = GitHubSource(github_token=github_token)

        self._registry = SkillsRegistry(
            sources=[local_source, github_source],
            install_dir=install_dir,
        )

    # ------------------------------------------------------------------
    # 子命令入口
    # ------------------------------------------------------------------

    async def cmd_search(
        self,
        query: str,
        source: str | None = None,
        limit: int = 20,
    ) -> list[SkillPackage]:
        """搜索 Skill 市场（Local + GitHub 两源并行）。

        Args:
            query: 搜索关键词（空字符串返回全部）
            source: 限定源（"local" | "github" | None = 全部）
            limit: 最大返回条数

        Returns:
            SkillPackage 列表（已按 installed 优先排序）
        """
        sources_filter = [source] if source else None
        results = await self._registry.search(query, sources=sources_filter)
        results = results[:limit]

        self._print_packages(results)
        return results

    async def cmd_install(
        self,
        package_id: str,
        source: str,
        version: str | None = None,
    ) -> InstalledSkill:
        """安装 Skill。

        流程：
        1. 调用 SkillsRegistry.install()（下载 → 解压 → 更新 registry.json）
        2. 若配置了 backend_url，发送 POST /api/v1/skills/install 同步 DB
        3. 输出安装结果

        注：DB 写入（skill_installs 表）由 Backend skill_install_service 完成（ADR-053）。
        """
        print(f"安装 Skill: {package_id} (source={source}, version={version or 'latest'})")

        installed = await self._registry.install(
            package_id=package_id,
            source=source,
            version=version,
        )

        print(f"[OK] 已安装: {installed.name} v{installed.version}")
        print(f"     路径: {installed.install_path}")
        print(f"     hooks: {installed.has_hooks}, mcp: {installed.has_mcp}")

        if self._backend_url:
            await self._notify_backend_install(installed)
        else:
            print(
                "[提示] 未配置 PRISM_BACKEND_URL，跳过 DB 同步。"
                " 生产环境请设置 PRISM_BACKEND_URL 并重新安装以写入 skill_installs 表。"
            )

        logger.info(
            "skills_cli.install",
            skill_name=installed.name,
            version=installed.version,
            source=source,
            has_hooks=installed.has_hooks,
            has_mcp=installed.has_mcp,
        )
        return installed

    async def cmd_uninstall(self, skill_name: str) -> None:
        """卸载 Skill（按 skill_name 查找并删除文件 + 更新 registry.json）。"""
        print(f"卸载 Skill: {skill_name}")
        await self._registry.uninstall(skill_name)
        print(f"[OK] 已卸载: {skill_name}")

        if self._backend_url:
            await self._notify_backend_uninstall(skill_name)
        else:
            print(
                "[提示] 未配置 PRISM_BACKEND_URL，跳过 DB 同步。"
                " 生产环境请设置 PRISM_BACKEND_URL 以更新 skill_installs 表状态。"
            )

        logger.info("skills_cli.uninstall", skill_name=skill_name)

    async def cmd_update(self, skill_name: str) -> InstalledSkill:
        """更新 Skill 到最新版本（卸载旧版 + 安装新版）。"""
        print(f"更新 Skill: {skill_name}")
        installed = await self._registry.update(skill_name)
        print(f"[OK] 已更新: {installed.name} v{installed.version}")
        logger.info(
            "skills_cli.update",
            skill_name=skill_name,
            new_version=installed.version,
        )
        return installed

    def cmd_list(self, source: str | None = None) -> list[InstalledSkill]:
        """列出已安装 Skills（从 registry.json 读取）。"""
        installed = self._registry.list_installed()

        if source:
            installed = [s for s in installed if s.source == source]

        if not installed:
            print("（无已安装 Skill）")
        else:
            print(f"已安装 Skills ({len(installed)} 个):")
            print(f"  {'名称':<30} {'版本':<12} {'源':<10} {'Hooks':<6} {'MCP'}")
            print("  " + "-" * 70)
            for skill in installed:
                print(
                    f"  {skill.name:<30} {skill.version:<12} {skill.source:<10}"
                    f" {'是' if skill.has_hooks else '否':<6} {'是' if skill.has_mcp else '否'}"
                )
        return installed

    async def cmd_info(self, skill_name: str) -> SkillPackage | None:
        """查看 Skill 详情（先从 registry 找，再搜索源）。"""
        # 先查已安装
        installed_list = self._registry.list_installed()
        installed = next((s for s in installed_list if s.name == skill_name), None)

        if installed:
            print(f"Skill: {skill_name}")
            print(f"  版本:      {installed.version}")
            print(f"  源:        {installed.source}")
            print(f"  源地址:    {installed.source_url}")
            print(f"  安装路径:  {installed.install_path}")
            print(f"  安装时间:  {installed.installed_at}")
            print(f"  Hooks:     {'是' if installed.has_hooks else '否'}")
            print(f"  MCP:       {'是' if installed.has_mcp else '否'}")
            print("  状态:      已安装")
            return None

        # 搜索源
        results = await self._registry.search(skill_name)
        match = next((p for p in results if p.name == skill_name), None)

        if match:
            self._print_packages([match])
        else:
            print(f"未找到 Skill: {skill_name}")

        return match

    # ------------------------------------------------------------------
    # Backend API 通知（ADR-053）
    # ------------------------------------------------------------------

    async def _notify_backend_install(self, skill: InstalledSkill) -> None:
        """向 Backend REST API 发送安装通知，写 skill_installs 表（ADR-053）。"""
        try:
            import httpx
        except ImportError:
            print("[警告] httpx 未安装，跳过 Backend API 通知。")
            return

        url = f"{self._backend_url.rstrip('/')}/api/v1/skills/install"
        payload = {
            "skill_name": skill.name,
            "source": skill.source,
            "source_url": skill.source_url,
            "version": skill.version,
            "install_path": skill.install_path,
            "has_hooks": skill.has_hooks,
            "has_mcp": skill.has_mcp,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 201):
                    print(f"[DB] skill_installs 表已同步（{resp.status_code}）。")
                else:
                    print(
                        f"[警告] Backend API 返回 {resp.status_code}，DB 同步可能失败。"
                        f" 响应: {resp.text[:200]}"
                    )
            except Exception as exc:
                print(f"[警告] Backend API 通知失败: {exc}")

    async def _notify_backend_uninstall(self, skill_name: str) -> None:
        """向 Backend REST API 发送卸载通知，更新 skill_installs 表状态（ADR-053）。"""
        try:
            import httpx
        except ImportError:
            print("[警告] httpx 未安装，跳过 Backend API 通知。")
            return

        url = f"{self._backend_url.rstrip('/')}/api/v1/skills/{skill_name}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.delete(url)
                if resp.status_code in (200, 204):
                    print(f"[DB] skill_installs 表状态已更新（{resp.status_code}）。")
                else:
                    print(
                        f"[警告] Backend API 返回 {resp.status_code}，DB 更新可能失败。"
                        f" 响应: {resp.text[:200]}"
                    )
            except Exception as exc:
                print(f"[警告] Backend API 通知失败: {exc}")

    # ------------------------------------------------------------------
    # 格式化输出
    # ------------------------------------------------------------------

    @staticmethod
    def _print_packages(packages: list[SkillPackage]) -> None:
        """格式化输出 SkillPackage 列表。"""
        if not packages:
            print("（无匹配结果）")
            return

        print(f"找到 {len(packages)} 个 Skill:")
        print(f"  {'名称':<30} {'版本':<12} {'源':<10} {'已安装':<6} {'描述'}")
        print("  " + "-" * 80)
        for pkg in packages:
            installed_mark = "✓" if pkg.installed else " "
            desc = pkg.description[:30] if pkg.description else ""
            print(
                f"  {pkg.name:<30} {pkg.version:<12} {pkg.source:<10}"
                f" {installed_mark:<6} {desc}"
            )


# ---------------------------------------------------------------------------
# CLI 入口（argparse）
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="prism skills",
        description="Prism Skills 命令行管理工具 (DOC-05 Task 5.6)",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("PRISM_WORKSPACE", _DEFAULT_WORKSPACE),
        help="工作目录根路径（默认 CWD）",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub Personal Access Token（也可通过 GITHUB_TOKEN 环境变量设置）",
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("PRISM_BACKEND_URL"),
        help="Backend REST API base URL（如 http://localhost:8000），用于同步 skill_installs 表",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="以 JSON 格式输出结果",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # search
    sp_search = subparsers.add_parser("search", help="搜索 Skill 市场")
    sp_search.add_argument("query", nargs="?", default="", help="搜索关键词（空 = 全部）")
    sp_search.add_argument(
        "--source",
        choices=["local", "github"],
        help="限定源（默认全部）",
    )
    sp_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="最大返回条数（默认 20）",
    )

    # install
    sp_install = subparsers.add_parser("install", help="安装 Skill")
    sp_install.add_argument("package_id", help="Skill 包 ID（如 user/repo 或本地 skill_name）")
    sp_install.add_argument(
        "--source",
        choices=["local", "github"],
        required=True,
        help="来源",
    )
    sp_install.add_argument("--version", help="指定版本（默认最新）")

    # uninstall
    sp_uninstall = subparsers.add_parser("uninstall", help="卸载 Skill")
    sp_uninstall.add_argument("skill_name", help="要卸载的 Skill 名称")

    # update
    sp_update = subparsers.add_parser("update", help="更新 Skill 到最新版本")
    sp_update.add_argument("skill_name", help="要更新的 Skill 名称")

    # list
    sp_list = subparsers.add_parser("list", help="列出已安装 Skills")
    sp_list.add_argument(
        "--source",
        choices=["local", "github"],
        help="按源过滤（默认全部）",
    )

    # info
    sp_info = subparsers.add_parser("info", help="查看 Skill 详情")
    sp_info.add_argument("skill_name", help="Skill 名称")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口，返回退出码。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    cli = SkillsCLI(
        workspace=args.workspace,
        github_token=args.github_token,
        backend_url=args.backend_url,
    )

    exit_code = 0

    try:
        if args.command == "search":
            asyncio.run(
                cli.cmd_search(
                    query=args.query,
                    source=getattr(args, "source", None),
                    limit=args.limit,
                )
            )

        elif args.command == "install":
            asyncio.run(
                cli.cmd_install(
                    package_id=args.package_id,
                    source=args.source,
                    version=getattr(args, "version", None),
                )
            )

        elif args.command == "uninstall":
            asyncio.run(cli.cmd_uninstall(args.skill_name))

        elif args.command == "update":
            asyncio.run(cli.cmd_update(args.skill_name))

        elif args.command == "list":
            cli.cmd_list(source=getattr(args, "source", None))

        elif args.command == "info":
            asyncio.run(cli.cmd_info(args.skill_name))

    except KeyboardInterrupt:
        print("\n[中止] 操作已取消。")
        exit_code = 130
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        logger.exception("skills_cli.error", command=args.command, error=str(exc))
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
