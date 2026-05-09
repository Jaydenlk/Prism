"""GitHub SkillSource — 搜索 GitHub 仓库中与 Skills 相关的项目。

使用 GitHub Repository Search API（无需认证），搜索仓库后验证
SKILL.md 存在性，确保结果是真正的 skill 而非普通项目。
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_REPOS_URL = "https://api.github.com/search/repositories"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)
_PLUGIN_PATHS = [
    "https://api.github.com/repos/{owner}/{repo}/contents/SKILL.md",
    "https://api.github.com/repos/{owner}/{repo}/contents/.claude-plugin/marketplace.json",
    "https://api.github.com/repos/{owner}/{repo}/contents/.claude-plugin/plugin.json",
]


async def _is_claude_plugin(client: httpx.AsyncClient, owner: str, repo: str) -> str | None:
    """Check if repo is a Claude skill/plugin. Returns type or None."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    for path in _PLUGIN_PATHS:
        try:
            resp = await client.head(path.format(owner=owner, repo=repo), headers=headers)
            if resp.status_code == 200:
                if "marketplace.json" in path:
                    return "marketplace"
                elif "plugin.json" in path:
                    return "plugin"
                else:
                    return "skill"
        except httpx.HTTPError:
            continue
    return None


class GitHubSource(SkillSource):

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        github_query = f"{query} in:name,description,readme"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _GITHUB_REPOS_URL,
                    params={"q": github_query, "per_page": 10, "sort": "stars"},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code != 200:
                    logger.warning("GitHub search returned %d", resp.status_code)
                    return []
                data = resp.json()

                candidates = data.get("items", [])
                checks = [
                    _is_claude_plugin(
                        client,
                        repo.get("owner", {}).get("login", ""),
                        repo.get("name", ""),
                    )
                    for repo in candidates
                ]
                plugin_types = await asyncio.gather(*checks)

        except httpx.HTTPError as exc:
            logger.warning("GitHub search failed: %s", exc)
            return []

        results: list[SkillPackage] = []
        for repo, ptype in zip(candidates, plugin_types):
            if not ptype:
                continue
            tags = repo.get("topics") or []
            if ptype not in tags:
                tags = [ptype] + tags
            results.append(SkillPackage(
                name=repo.get("name", ""),
                description=repo.get("description") or "",
                version="latest",
                source="github",
                source_url=repo.get("html_url", ""),
                author=repo.get("owner", {}).get("login"),
                tags=tags,
                stars=repo.get("stargazers_count", 0),
            ))
        return results

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub install uses marketplace clone flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
