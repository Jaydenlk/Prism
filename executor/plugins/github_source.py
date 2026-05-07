"""GitHub SkillSource — 搜索 GitHub 仓库中的 SKILL.md 文件。

用户需求覆盖 fix#3+（删除 GitHubSource）决策：用户明确要求以 Manus + GitHub 为主。
"""
from __future__ import annotations

import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_SEARCH_URL = "https://api.github.com/search/code"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)


class GitHubSource(SkillSource):

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _GITHUB_SEARCH_URL,
                    params={"q": f"filename:SKILL.md {query}", "per_page": 20},
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
        seen: set[str] = set()
        for item in data.get("items", []):
            repo = item.get("repository", {})
            full_name = repo.get("full_name", "")
            if full_name in seen:
                continue
            seen.add(full_name)
            path = item.get("path", "")
            skill_name = path.split("/")[-2] if "/" in path else full_name.split("/")[-1]
            results.append(SkillPackage(
                name=skill_name,
                description=repo.get("description") or "",
                version="latest",
                source="github",
                source_url=repo.get("html_url", f"https://github.com/{full_name}"),
                author=repo.get("owner", {}).get("login"),
                tags=repo.get("topics") or [],
            ))
        return results

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub install uses marketplace clone flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
