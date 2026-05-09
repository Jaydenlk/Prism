"""GitHub SkillSource — search GitHub repos for Claude Code skills/plugins.

Uses GitHub Repository Search API (unauthenticated, 10 req/min).
Returns results directly without per-repo validation to avoid rate limits.
"""
from __future__ import annotations

import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_REPOS_URL = "https://api.github.com/search/repositories"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)

_CLAUDE_TOPICS = {"claude-code", "claude-plugin", "claude-skill", "mcp-server", "claude-code-plugin", "skill"}


def _infer_type(topics: list[str], name: str, desc: str) -> str:
    """Infer whether a repo is a skill, plugin, or marketplace from metadata."""
    t_set = set(topics)
    combined = (name + " " + desc).lower()
    if t_set & {"claude-plugin", "claude-code-plugin"}:
        return "plugin"
    if "marketplace" in combined or "registry" in combined:
        return "marketplace"
    if t_set & {"claude-skill", "skill"}:
        return "skill"
    if t_set & {"mcp-server", "mcp"}:
        return "mcp"
    if any(kw in combined for kw in ("skill", "plugin", "claude-code", "agent")):
        return "plugin"
    return "repo"


class GitHubSource(SkillSource):

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        github_query = f"{query} in:name,description"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _GITHUB_REPOS_URL,
                    params={"q": github_query, "per_page": 15, "sort": "stars"},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code == 403:
                    logger.warning("GitHub API rate limited")
                    return []
                if resp.status_code != 200:
                    logger.warning("GitHub search returned %d", resp.status_code)
                    return []
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("GitHub search failed: %s", exc)
            return []

        results: list[SkillPackage] = []
        for repo in data.get("items", []):
            topics = repo.get("topics") or []
            name = repo.get("name", "")
            desc = repo.get("description") or ""
            ptype = _infer_type(topics, name, desc)
            tags = [ptype] + topics[:5] if ptype not in topics else topics[:6]
            stars = repo.get("stargazers_count", 0)
            results.append(SkillPackage(
                name=name,
                description=desc,
                version="latest",
                source="github",
                source_url=repo.get("html_url", ""),
                author=repo.get("owner", {}).get("login"),
                tags=tags,
                stars=stars,
            ))
        results.sort(key=lambda p: p.stars or 0, reverse=True)
        return results[:3]

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub install uses marketplace clone flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
