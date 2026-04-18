"""
Skills 多源聚合注册表

DOC-05 Task 5.5: Skills Registry & Multi-Source Aggregation（ADR-051）
ADR-051 (PRD 原标 ADR-047 平移): Phase 1 仅 Local + GitHub 两源。
  - NpmSource / ManusSource 推迟到 Phase 2（抽象基类已预留扩展点）
  - 去重策略：按 Skill name 去重，已安装版本优先展示
  - 跨源并行搜索（asyncio.gather）

来源: Master M8, Batch 2 §A5-5; PRD DOC-05 v4 Task 5.5 Part A

进程边界：本模块只 import executor.* + stdlib + httpx，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import httpx
import structlog
import yaml

from executor.plugins.skill_types import SkillMetadata

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 数据类型定义
# ---------------------------------------------------------------------------


@dataclass
class SkillPackage:
    """Skills 搜索结果条目（v4）

    source 字段枚举收窄为 Literal["local", "github"]（Phase 1 仅两源）。
    """

    name: str                           # Skill 名称
    description: str                    # 简短描述
    version: str                        # 版本号
    source: Literal["local", "github"]  # v4: Phase 1 只两种
    source_url: str                     # 源地址（本地目录路径或 GitHub repo URL）
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    installed: bool = False             # 是否已安装
    installed_version: str | None = None


@dataclass
class SkillBundle:
    """下载后的 Skill 包（待安装）

    files: 文件路径（相对 skill 根目录）→ 内容字节
    plugin_config: 如果是完整 Plugin 而非单个 Skill，包含 plugin.yaml 内容
    """

    metadata: SkillPackage
    files: dict[str, bytes]            # 文件路径 → 内容
    plugin_config: dict | None = None  # 如果是完整插件而非单个 Skill


@dataclass
class InstalledSkill:
    """已安装的 Skill

    记录 Skill 安装信息，对应 skill_installs 表的展示视图（executor 侧不直接写 DB）。
    """

    name: str
    version: str
    source: str
    source_url: str
    install_path: str
    installed_at: str                  # ISO 8601
    has_hooks: bool
    has_mcp: bool


# ---------------------------------------------------------------------------
# SkillSource 抽象基类（Phase 2 扩展点）
# ---------------------------------------------------------------------------


class SkillSource(ABC):
    """Skills 源抽象基类

    Phase 1 实现：LocalSource / GitHubSource。
    Phase 2 预留扩展：NpmSource / ManusSource（见文件末尾占位注释）。
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """源名称（用于 SkillPackage.source 字段）"""
        ...

    @abstractmethod
    async def search(self, query: str) -> list[SkillPackage]:
        """搜索 Skill，返回匹配的 SkillPackage 列表（空查询返回全部）。"""
        ...

    @abstractmethod
    async def fetch(
        self, package_id: str, version: str | None = None
    ) -> SkillBundle:
        """下载指定 Skill，返回 SkillBundle（含文件内容字节）。"""
        ...

    @abstractmethod
    async def get_versions(self, package_id: str) -> list[str]:
        """获取 Skill 的可用版本列表（最新版在前）。"""
        ...


# ---------------------------------------------------------------------------
# LocalSource — 本地目录扫描
# ---------------------------------------------------------------------------


class LocalSource(SkillSource):
    """本地 .skills/ 目录扫描（CC 兼容模式）

    扫描路径：
    1. {workspace}/.skills/          — CC 兼容的自动加载目录
    2. {workspace}/.prism/skills/    — Prism 管理的已安装 Skills

    搜索方式：遍历目录，匹配 SKILL.md 的 name/description/tags
    """

    source_name: str = "local"  # type: ignore[assignment]

    def __init__(self, workspace: str = "") -> None:
        """
        Args:
            workspace: 工作目录根路径（默认取 CWD）
        """
        self._workspace = workspace or os.getcwd()
        self._scan_dirs: list[str] = [
            os.path.join(self._workspace, ".skills"),
            os.path.join(self._workspace, ".prism", "skills"),
        ]

    async def search(self, query: str) -> list[SkillPackage]:
        """遍历本地 .skills/ 目录，匹配 query 关键词（name / description / tags）。

        query 为空时返回全部本地 Skill。
        """
        results: list[SkillPackage] = []
        seen: set[str] = set()

        for scan_dir in self._scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            for entry in os.listdir(scan_dir):
                skill_dir = os.path.join(scan_dir, entry)
                skill_file = os.path.join(skill_dir, "SKILL.md")
                if not (os.path.isdir(skill_dir) and os.path.exists(skill_file)):
                    continue

                pkg = self._parse_skill_package(skill_file, skill_dir)
                if pkg is None:
                    continue
                if pkg.name in seen:
                    continue  # 去重（.prism/skills/ 优先，先出现的保留）
                seen.add(pkg.name)

                if self._matches(pkg, query):
                    results.append(pkg)

        logger.debug(
            "local_source.search",
            query=query,
            found=len(results),
        )
        return results

    async def fetch(
        self, package_id: str, version: str | None = None
    ) -> SkillBundle:
        """从本地目录读取 Skill 内容，返回 SkillBundle。

        package_id 为 Skill name（从 frontmatter 解析）。
        version 参数在本地源中忽略（本地无版本管理）。
        """
        for scan_dir in self._scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            for entry in os.listdir(scan_dir):
                skill_dir = os.path.join(scan_dir, entry)
                skill_file = os.path.join(skill_dir, "SKILL.md")
                if not (os.path.isdir(skill_dir) and os.path.exists(skill_file)):
                    continue
                pkg = self._parse_skill_package(skill_file, skill_dir)
                if pkg is not None and pkg.name == package_id:
                    files = self._read_skill_files(skill_dir)
                    return SkillBundle(metadata=pkg, files=files)

        raise FileNotFoundError(
            f"LocalSource: Skill '{package_id}' not found in {self._scan_dirs}"
        )

    async def get_versions(self, package_id: str) -> list[str]:
        """本地源不支持版本管理，返回唯一版本号（从 frontmatter 读取）。"""
        bundle = await self.fetch(package_id)
        return [bundle.metadata.version]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _parse_skill_package(
        self, skill_file: str, skill_dir: str
    ) -> SkillPackage | None:
        """解析 SKILL.md frontmatter，构建 SkillPackage。失败返回 None。"""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            logger.warning(
                "local_source.parse_error", file=skill_file, error=str(exc)
            )
            return None

        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end == -1:
            return None

        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError as exc:
            logger.warning(
                "local_source.yaml_error", file=skill_file, error=str(exc)
            )
            return None

        name = fm.get("name")
        if not name:
            return None

        return SkillPackage(
            name=str(name),
            description=str(fm.get("description", "")),
            version=str(fm.get("version", "local")),
            source="local",
            source_url=skill_dir,
            author=fm.get("author"),
            tags=list(fm.get("tags", [])),
        )

    def _matches(self, pkg: SkillPackage, query: str) -> bool:
        """检查 SkillPackage 是否匹配搜索关键词（大小写不敏感）。

        query 为空时匹配全部。
        """
        if not query:
            return True
        q = query.lower()
        return (
            q in pkg.name.lower()
            or q in pkg.description.lower()
            or any(q in tag.lower() for tag in pkg.tags)
        )

    def _read_skill_files(self, skill_dir: str) -> dict[str, bytes]:
        """读取 Skill 目录内所有文件，返回 {相对路径 → 字节内容} dict。"""
        files: dict[str, bytes] = {}
        for root, _dirs, filenames in os.walk(skill_dir):
            for fname in filenames:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, skill_dir)
                try:
                    with open(abs_path, "rb") as f:
                        files[rel_path] = f.read()
                except OSError as exc:
                    logger.warning(
                        "local_source.read_file_error",
                        path=abs_path,
                        error=str(exc),
                    )
        return files


# ---------------------------------------------------------------------------
# GitHubSource — GitHub 仓库直接安装
# ---------------------------------------------------------------------------


# GitHub API 相关常量
_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
_DEFAULT_GITHUB_TIMEOUT = 30.0


class GitHubSource(SkillSource):
    """GitHub 仓库直接安装

    支持格式：
    - github:user/repo               — 默认分支的根目录
    - github:user/repo#branch        — 指定分支
    - github:user/repo@v1.0.0        — 指定 tag
    - github:user/repo/path/to/skill — 仓库内子目录

    实现：通过 GitHub API 获取目录树，通过 raw.githubusercontent.com 下载文件。

    认证：可选 GITHUB_TOKEN 环境变量（提升 API 速率限制 60→5000 req/h）。
    """

    source_name: str = "github"  # type: ignore[assignment]

    def __init__(
        self,
        github_token: str | None = None,
        timeout: float = _DEFAULT_GITHUB_TIMEOUT,
    ) -> None:
        """
        Args:
            github_token: GitHub Personal Access Token（可选，优先级高于环境变量）
            timeout: HTTP 请求超时秒数
        """
        token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout

    async def search(self, query: str) -> list[SkillPackage]:
        """通过 GitHub Code Search API 搜索 SKILL.md 文件。

        搜索关键词 query 追加 "filename:SKILL.md" 限定。
        返回最多 30 条结果（GitHub API 单次限额）。
        注意：需要 GitHub Token 才能调用 code search API（rate limit 严格）。
        无 Token 时返回空列表并 log warning。
        """
        if "Authorization" not in self._headers:
            logger.warning(
                "github_source.search.no_token",
                hint="Set GITHUB_TOKEN env var to enable GitHub search",
            )
            return []

        search_query = f"{query} filename:SKILL.md" if query else "filename:SKILL.md"
        url = f"{_GITHUB_API_BASE}/search/code"
        params = {"q": search_query, "per_page": 30}

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "github_source.search.http_error",
                    status=exc.response.status_code,
                    query=query,
                )
                return []
            except httpx.RequestError as exc:
                logger.warning(
                    "github_source.search.request_error",
                    error=str(exc),
                    query=query,
                )
                return []

        data = resp.json()
        items = data.get("items", [])
        results: list[SkillPackage] = []
        seen: set[str] = set()

        for item in items:
            repo = item.get("repository", {})
            repo_full = repo.get("full_name", "")
            file_path = item.get("path", "")
            html_url = item.get("html_url", "")

            # 尝试获取 SKILL.md frontmatter 来拿 name/description
            pkg = await self._fetch_skill_package_from_search_item(
                repo_full, file_path
            )
            if pkg is None:
                # 降级：用 repo name 作为 skill name
                pkg = SkillPackage(
                    name=repo_full.replace("/", "__") or file_path,
                    description=repo.get("description") or "",
                    version="latest",
                    source="github",
                    source_url=html_url,
                )

            if pkg.name not in seen:
                seen.add(pkg.name)
                results.append(pkg)

        logger.info(
            "github_source.search",
            query=query,
            found=len(results),
        )
        return results

    async def fetch(
        self, package_id: str, version: str | None = None
    ) -> SkillBundle:
        """从 GitHub 下载 Skill 文件，返回 SkillBundle。

        package_id 格式：
        - "user/repo"               — 根目录，默认分支
        - "user/repo#branch"        — 指定分支
        - "user/repo@v1.0.0"        — 指定 tag
        - "user/repo/path/to/skill" — 仓库内子目录

        实现：通过 GitHub API 获取 tree，逐文件 raw download。
        """
        repo, ref, subpath = self._parse_package_id(package_id)

        # 获取默认分支（如果 ref 未指定）
        if not ref:
            ref = await self._get_default_branch(repo)

        # 获取目录树
        files = await self._download_skill_files(repo, ref, subpath)

        # 解析 SKILL.md 获取元数据
        skill_md_content = files.get("SKILL.md")
        if skill_md_content is None:
            raise FileNotFoundError(
                f"GitHubSource: SKILL.md not found in {package_id}"
            )

        skill_md_text = skill_md_content.decode("utf-8", errors="replace")
        pkg = self._parse_frontmatter_text(
            skill_md_text,
            source_url=f"https://github.com/{repo}",
            version=version or ref,
        )
        if pkg is None:
            pkg = SkillPackage(
                name=repo.replace("/", "__"),
                description="",
                version=version or ref,
                source="github",
                source_url=f"https://github.com/{repo}",
            )

        return SkillBundle(metadata=pkg, files=files)

    async def get_versions(self, package_id: str) -> list[str]:
        """获取 GitHub 仓库的 tag 列表（作为版本列表）。

        package_id 格式与 fetch() 相同。
        返回列表：最新 tag 在前，最多返回 20 条。
        若无 tag，返回 ["latest"]（默认分支）。
        """
        repo, _ref, _subpath = self._parse_package_id(package_id)
        url = f"{_GITHUB_API_BASE}/repos/{repo}/tags"

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(url, params={"per_page": 20})
                resp.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning(
                    "github_source.get_versions.error",
                    repo=repo,
                    error=str(exc),
                )
                return ["latest"]

        tags = resp.json()
        versions = [t.get("name", "") for t in tags if t.get("name")]
        return versions if versions else ["latest"]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_package_id(package_id: str) -> tuple[str, str, str]:
        """解析 package_id 为 (repo, ref, subpath)。

        格式:
        - "user/repo"               → ("user/repo", "", "")
        - "user/repo#branch"        → ("user/repo", "branch", "")
        - "user/repo@v1.0.0"        → ("user/repo", "v1.0.0", "")
        - "user/repo/path/to/skill" → ("user/repo", "", "path/to/skill")
        - "github:user/repo"        → 去掉前缀 "github:"

        返回 (repo_full_name, ref, subpath)。
        """
        pid = package_id
        if pid.startswith("github:"):
            pid = pid[len("github:"):]

        # 先提取 ref（# 或 @）
        ref = ""
        if "#" in pid:
            pid, ref = pid.split("#", 1)
        elif "@" in pid:
            # 注意：repo 本身不含 @，tag/branch 可能包含 v1.0.0 格式
            # user/repo@v1.0.0 → repo="user/repo", ref="v1.0.0"
            at_idx = pid.rfind("@")
            before_at = pid[:at_idx]
            # 只有当 @ 前至少有一个 / （即 user/repo 格式）才提取 ref
            if before_at.count("/") >= 1:
                pid = before_at
                ref = package_id[package_id.rfind("@") + 1:]

        # 分离 repo（前两段 user/repo）和 subpath（后续路径）
        parts = pid.split("/")
        if len(parts) >= 2:
            repo = "/".join(parts[:2])
            subpath = "/".join(parts[2:])
        else:
            repo = pid
            subpath = ""

        return repo, ref, subpath

    async def _get_default_branch(self, repo: str) -> str:
        """获取仓库的默认分支名（通常是 main 或 master）。"""
        url = f"{_GITHUB_API_BASE}/repos/{repo}"
        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json().get("default_branch", "main")
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning(
                    "github_source.get_default_branch.error",
                    repo=repo,
                    error=str(exc),
                )
                return "main"

    async def _download_skill_files(
        self, repo: str, ref: str, subpath: str
    ) -> dict[str, bytes]:
        """通过 GitHub API tree 接口获取目录文件列表，下载所有文件。

        返回 {相对路径 → 字节内容} dict。
        subpath 为仓库内子目录（空表示根目录）。

        采用并发下载（asyncio.gather）加速。
        """
        tree_url = f"{_GITHUB_API_BASE}/repos/{repo}/git/trees/{ref}?recursive=1"
        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(tree_url)
                resp.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                raise RuntimeError(
                    f"GitHubSource: failed to fetch tree for {repo}@{ref}: {exc}"
                ) from exc

        tree_data = resp.json()
        tree_items = tree_data.get("tree", [])

        # 过滤出 subpath 下的文件
        file_items: list[tuple[str, str]] = []  # (rel_path, sha/download_url)
        for item in tree_items:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if subpath:
                if not path.startswith(subpath.rstrip("/") + "/"):
                    # 允许正好是 subpath/SKILL.md 这类情况
                    if path != subpath + "/SKILL.md" and path != subpath:
                        continue
                rel = path[len(subpath.rstrip("/") + "/"):]
            else:
                rel = path
            if not rel:
                continue
            raw_url = (
                f"{_GITHUB_RAW_BASE}/{repo}/{ref}/{path}"
            )
            file_items.append((rel, raw_url))

        if not file_items:
            raise FileNotFoundError(
                f"GitHubSource: no files found at {repo}/{subpath} @ {ref}"
            )

        # 并发下载
        async def _download(rel_path: str, url: str) -> tuple[str, bytes]:
            async with httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout
            ) as cl:
                try:
                    r = await cl.get(url)
                    r.raise_for_status()
                    return rel_path, r.content
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    logger.warning(
                        "github_source.download_file.error",
                        url=url,
                        error=str(exc),
                    )
                    return rel_path, b""

        results = await asyncio.gather(*[_download(rp, u) for rp, u in file_items])
        return {rp: content for rp, content in results if content}

    async def _fetch_skill_package_from_search_item(
        self, repo_full: str, file_path: str
    ) -> SkillPackage | None:
        """从 GitHub Code Search 结果中下载 SKILL.md，解析 frontmatter。

        失败时返回 None（降级处理）。
        """
        # 获取默认分支
        branch = await self._get_default_branch(repo_full)
        raw_url = f"{_GITHUB_RAW_BASE}/{repo_full}/{branch}/{file_path}"

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(raw_url)
                resp.raise_for_status()
                text = resp.text
            except (httpx.HTTPStatusError, httpx.RequestError):
                return None

        return self._parse_frontmatter_text(
            text,
            source_url=f"https://github.com/{repo_full}",
            version="latest",
        )

    @staticmethod
    def _parse_frontmatter_text(
        text: str,
        source_url: str,
        version: str,
    ) -> SkillPackage | None:
        """从 SKILL.md 文本解析 frontmatter，构建 SkillPackage。"""
        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end == -1:
            return None
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError:
            return None

        name = fm.get("name")
        if not name:
            return None

        return SkillPackage(
            name=str(name),
            description=str(fm.get("description", "")),
            version=str(fm.get("version", version)),
            source="github",
            source_url=source_url,
            author=fm.get("author"),
            tags=list(fm.get("tags", [])),
        )


# Phase 2 预留扩展点（禁止在 Phase 1 实现）：
# class NpmSource(SkillSource): ...    # Phase 2: npm 包安装（需容器内 npm + 安全审计）
# class ManusSource(SkillSource): ...  # Phase 2: Manus API（契约未稳定）


# ---------------------------------------------------------------------------
# SkillsRegistry — 多源聚合注册表
# ---------------------------------------------------------------------------


class SkillsRegistry:
    """Skills 多源聚合注册表（ADR-051）

    职责：
    1. 跨源并行搜索（asyncio.gather）+ 合并去重
    2. 安装 Skill（fetch → 验证 → 解压 → 注册 → 更新 registry.json）
    3. 卸载 Skill（注销 hooks/MCP → 删文件 → 更新 registry.json）
    4. 列出已安装 Skills（from registry.json）
    5. 通知 PluginHost reload（安装/卸载后）

    去重策略（ADR-051）：
    - 跨源按 Skill name 去重
    - 已安装的 Skill 排在前面（installed=True 优先展示）
    - 同名多源时展示已安装版本

    安装目录结构（见 PRD Part A §安装目录结构）：
        {install_dir}/
        ├── registry.json        — 已安装 Skills 索引
        ├── @github/             — GitHub 源安装的 Skills
        │   └── user__repo/
        │       └── SKILL.md
        └── @local/              — 本地源安装（复制到管理目录）
            └── skill_name/
                └── SKILL.md
    """

    def __init__(
        self,
        sources: list[SkillSource],
        install_dir: str,
        registry_file: str = "",
    ) -> None:
        """
        Args:
            sources: SkillSource 列表（LocalSource + GitHubSource）
            install_dir: 已安装 Skills 的根目录（.prism/skills/）
            registry_file: registry.json 路径；默认为 {install_dir}/registry.json
        """
        self._sources: dict[str, SkillSource] = {s.source_name: s for s in sources}
        self._install_dir = install_dir
        self._registry_file = registry_file or os.path.join(install_dir, "registry.json")
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
    ) -> list[SkillPackage]:
        """跨源并行搜索，合并去重（ADR-051）。

        Args:
            query: 搜索关键词（空字符串返回全部）
            sources: 指定源列表（None = 全部源）

        去重策略：
        1. 按 name 去重（首次出现的记录保留）
        2. 已安装版本优先展示（installed=True 排前面）
        3. 跨源同名时，标记 installed 状态
        """
        active_sources = self._get_active_sources(sources)
        installed = {s.name: s for s in self.list_installed()}

        # 并行搜索各源
        tasks = [src.search(query) for src in active_sources]
        source_results: list[list[SkillPackage]] = list(
            await asyncio.gather(*tasks, return_exceptions=False)
        )

        # 合并去重（按 name，已安装优先）
        merged: dict[str, SkillPackage] = {}
        for pkgs in source_results:
            for pkg in pkgs:
                # 标记 installed 状态
                if pkg.name in installed:
                    pkg.installed = True
                    pkg.installed_version = installed[pkg.name].version

                if pkg.name not in merged:
                    merged[pkg.name] = pkg
                else:
                    # 同名时：已安装版本优先（installed=True 替换 installed=False）
                    existing = merged[pkg.name]
                    if pkg.installed and not existing.installed:
                        merged[pkg.name] = pkg

        # 已安装的排前面，其余按 name 字母序
        result = sorted(
            merged.values(),
            key=lambda p: (0 if p.installed else 1, p.name),
        )

        logger.info(
            "skills_registry.search",
            query=query,
            sources=[s.source_name for s in active_sources],
            found=len(result),
        )
        return result

    # ------------------------------------------------------------------
    # 安装
    # ------------------------------------------------------------------

    async def install(
        self,
        package_id: str,
        source: str,
        version: str | None = None,
    ) -> InstalledSkill:
        """从指定源安装 Skill。

        流程：
        1. 从源 fetch SkillBundle
        2. 验证 SKILL.md frontmatter 格式（必须含 name 字段）
        3. 解压到 {install_dir}/@{source}/{safe_name}/
        4. 如果包含 hooks → 检测 has_hooks=True
        5. 如果包含 mcp/ 目录 → 检测 has_mcp=True
        6. 更新 registry.json
        7. 返回 InstalledSkill

        注：Hook 注册和 MCP 启动由上层 PluginHost 负责（executor 进程中）。
            Backend skill_install_service 调用本方法后再写 skill_installs 表。
        """
        src = self._get_source(source)
        bundle = await src.fetch(package_id, version=version)

        # 验证
        skill_md = bundle.files.get("SKILL.md")
        if skill_md is None:
            raise ValueError(
                f"SkillsRegistry: bundle from '{package_id}' missing SKILL.md"
            )

        pkg = bundle.metadata
        has_hooks = self._bundle_has_hooks(bundle)
        has_mcp = self._bundle_has_mcp(bundle)

        # 解压到安装目录
        safe_name = self._safe_dirname(package_id)
        scope_dir = os.path.join(self._install_dir, f"@{source}")
        install_path = os.path.join(scope_dir, safe_name)

        os.makedirs(install_path, exist_ok=True)
        for rel_path, content in bundle.files.items():
            abs_path = os.path.join(install_path, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(content)

        from datetime import datetime, timezone

        installed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        installed_skill = InstalledSkill(
            name=pkg.name,
            version=pkg.version,
            source=source,
            source_url=pkg.source_url,
            install_path=install_path,
            installed_at=installed_at,
            has_hooks=has_hooks,
            has_mcp=has_mcp,
        )

        # 更新 registry.json
        self._update_registry(installed_skill)

        logger.info(
            "skills_registry.install",
            name=pkg.name,
            version=pkg.version,
            source=source,
            install_path=install_path,
            has_hooks=has_hooks,
            has_mcp=has_mcp,
        )
        return installed_skill

    # ------------------------------------------------------------------
    # 卸载
    # ------------------------------------------------------------------

    async def uninstall(self, skill_id: str) -> None:
        """卸载 Skill（按 name 查找）。

        流程：
        1. 从 registry.json 查找已安装 Skill
        2. 删除安装目录文件
        3. 更新 registry.json（移除条目）

        注：Hook 注销和 MCP 停止由上层 PluginHost.unload_plugin() 负责。
        """
        registry = self._load_registry()
        skill = next((s for s in registry if s["name"] == skill_id), None)
        if skill is None:
            logger.warning("skills_registry.uninstall.not_found", skill_id=skill_id)
            return

        install_path = skill.get("install_path", "")
        if install_path and os.path.isdir(install_path):
            shutil.rmtree(install_path, ignore_errors=True)
            logger.info(
                "skills_registry.uninstall.files_removed",
                skill_id=skill_id,
                install_path=install_path,
            )

        # 更新 registry.json
        new_registry = [s for s in registry if s["name"] != skill_id]
        self._save_registry(new_registry)

        logger.info("skills_registry.uninstall", skill_id=skill_id)

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    async def update(self, skill_id: str) -> InstalledSkill:
        """更新到最新版本（卸载旧版 + 安装新版）。"""
        registry = self._load_registry()
        skill = next((s for s in registry if s["name"] == skill_id), None)
        if skill is None:
            raise ValueError(
                f"SkillsRegistry: Skill '{skill_id}' not installed, cannot update"
            )

        source = skill.get("source", "local")
        source_url = skill.get("source_url", skill_id)

        # 卸载旧版
        await self.uninstall(skill_id)

        # 安装新版（version=None 获取最新）
        return await self.install(source_url, source=source, version=None)

    # ------------------------------------------------------------------
    # 列出已安装
    # ------------------------------------------------------------------

    def list_installed(self) -> list[InstalledSkill]:
        """列出所有已安装 Skills（从 registry.json 读取）。"""
        registry = self._load_registry()
        result: list[InstalledSkill] = []
        for entry in registry:
            try:
                result.append(
                    InstalledSkill(
                        name=entry["name"],
                        version=entry.get("version", "unknown"),
                        source=entry.get("source", "local"),
                        source_url=entry.get("source_url", ""),
                        install_path=entry.get("install_path", ""),
                        installed_at=entry.get("installed_at", ""),
                        has_hooks=bool(entry.get("has_hooks", False)),
                        has_mcp=bool(entry.get("has_mcp", False)),
                    )
                )
            except (KeyError, TypeError) as exc:
                logger.warning(
                    "skills_registry.list_installed.parse_error",
                    entry=entry,
                    error=str(exc),
                )
        return result

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """确保安装目录存在。"""
        os.makedirs(self._install_dir, exist_ok=True)

    def _get_active_sources(
        self, source_filter: list[str] | None
    ) -> list[SkillSource]:
        """返回过滤后的 SkillSource 列表。None 表示全部。"""
        if source_filter is None:
            return list(self._sources.values())
        active: list[SkillSource] = []
        for name in source_filter:
            if name in self._sources:
                active.append(self._sources[name])
            else:
                logger.warning(
                    "skills_registry.unknown_source",
                    source=name,
                    available=list(self._sources.keys()),
                )
        return active

    def _get_source(self, source: str) -> SkillSource:
        """获取指定 source 的 SkillSource 实例，不存在则 raise ValueError。"""
        src = self._sources.get(source)
        if src is None:
            raise ValueError(
                f"SkillsRegistry: unknown source '{source}'. "
                f"Available: {list(self._sources.keys())}"
            )
        return src

    def _load_registry(self) -> list[dict]:
        """从 registry.json 加载已安装 Skill 列表。文件不存在时返回空列表。"""
        if not os.path.exists(self._registry_file):
            return []
        try:
            with open(self._registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("skills", [])
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "skills_registry.registry_load_error",
                path=self._registry_file,
                error=str(exc),
            )
            return []

    def _save_registry(self, skills: list[dict]) -> None:
        """将 skills 列表写入 registry.json（原子写：先写临时文件，再 rename）。"""
        data = {"version": "1.0", "skills": skills}
        tmp_path = self._registry_file + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # 原子 rename
            if os.path.exists(self._registry_file):
                os.replace(tmp_path, self._registry_file)
            else:
                os.rename(tmp_path, self._registry_file)
        except OSError as exc:
            logger.error(
                "skills_registry.registry_save_error",
                path=self._registry_file,
                error=str(exc),
            )
            raise

    def _update_registry(self, skill: InstalledSkill) -> None:
        """在 registry.json 中添加或更新一条 Skill 记录（按 name 去重覆盖）。"""
        registry = self._load_registry()
        entry = {
            "name": skill.name,
            "version": skill.version,
            "source": skill.source,
            "source_url": skill.source_url,
            "install_path": skill.install_path,
            "installed_at": skill.installed_at,
            "has_hooks": skill.has_hooks,
            "has_mcp": skill.has_mcp,
        }
        # 替换同名条目（若已存在）
        new_registry = [s for s in registry if s.get("name") != skill.name]
        new_registry.append(entry)
        self._save_registry(new_registry)

    @staticmethod
    def _safe_dirname(package_id: str) -> str:
        """将 package_id 转为安全的目录名（替换 / 和 : 等特殊字符）。"""
        # 去掉 scheme 前缀（如 "github:"）
        pid = package_id
        if ":" in pid:
            pid = pid.split(":", 1)[1]
        return pid.replace("/", "__").replace("#", "_").replace("@", "").strip("_")

    @staticmethod
    def _bundle_has_hooks(bundle: SkillBundle) -> bool:
        """检测 SkillBundle 是否包含 hooks 配置（hooks/ 目录或 SKILL.md frontmatter hooks）。"""
        # 检查文件路径中是否有 hooks/ 目录
        has_hooks_dir = any(
            k.startswith("hooks/") for k in bundle.files
        )
        # 检查 SKILL.md frontmatter 中的 hooks 字段
        skill_md = bundle.files.get("SKILL.md", b"")
        text = skill_md.decode("utf-8", errors="replace")
        has_hooks_fm = (
            "hooks:" in text
            and text.startswith("---")
            and text.find("---", 3) != -1
        )
        return has_hooks_dir or has_hooks_fm

    @staticmethod
    def _bundle_has_mcp(bundle: SkillBundle) -> bool:
        """检测 SkillBundle 是否包含 MCP 配置（mcp/ 或 mcp-servers/ 目录）。"""
        return any(
            k.startswith("mcp/") or k.startswith("mcp-servers/")
            for k in bundle.files
        )
