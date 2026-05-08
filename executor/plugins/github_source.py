"""GitHub SkillSource — 搜索 GitHub 仓库中与 Skills 相关的项目。

使用 GitHub Repository Search API（无需认证），搜索描述或 README 中
包含 skill/SKILL.md 关键词的仓库。
"""
from __future__ import annotations

import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_REPOS_URL = "https://api.github.com/search/repositories"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)


class GitHubSource(SkillSource):

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        github_query = f"{query} in:name,description,readme topic:skill"
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
        except httpx.HTTPError as exc:
            logger.warning("GitHub search failed: %s", exc)
            return []

        results: list[SkillPackage] = []
        for repo in data.get("items", []):
            results.append(SkillPackage(
                name=repo.get("name", ""),
                description=repo.get("description") or "",
                version="latest",
                source="github",
                source_url=repo.get("html_url", ""),
                author=repo.get("owner", {}).get("login"),
                tags=repo.get("topics") or [],
                stars=repo.get("stargazers_count", 0),
            ))
        return results

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub install uses marketplace clone flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
