"""GitHub SkillSource — dual-query search with "did you mean?" suggestion.

Strategy:
1. Exact name match: `{query} in:name`
2. Claude-scoped match: `{query} claude skill plugin mcp in:name,description,topics`
3. If top result < 1000 stars → fuzzy search for high-star similar names
4. Merge, dedup, sort by stars, return top 5
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_REPOS_URL = "https://api.github.com/search/repositories"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)


def _infer_type(topics: list[str], name: str, desc: str) -> str:
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


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def _is_similar(query: str, name: str) -> bool:
    """Check if name is a plausible typo of query (edit distance <= 2)."""
    q = query.lower()
    n = name.lower()
    if q == n:
        return False
    return _edit_distance(q, n) <= 2


async def _search_github(client: httpx.AsyncClient, query: str, per_page: int = 10) -> list[dict]:
    try:
        resp = await client.get(
            _GITHUB_REPOS_URL,
            params={"q": query, "per_page": per_page, "sort": "stars", "order": "desc"},
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code in (403, 422):
            logger.warning("GitHub search returned %d for query: %s", resp.status_code, query[:50])
            return []
        if resp.status_code != 200:
            logger.warning("GitHub search returned %d", resp.status_code)
            return []
        return resp.json().get("items", [])
    except httpx.HTTPError as exc:
        logger.warning("GitHub search failed: %s", exc)
        return []


def _repo_to_package(repo: dict) -> SkillPackage:
    topics = repo.get("topics") or []
    name = repo.get("name", "")
    desc = repo.get("description") or ""
    ptype = _infer_type(topics, name, desc)
    tags = [ptype] + topics[:5] if ptype not in topics else topics[:6]
    return SkillPackage(
        name=name,
        description=desc,
        version="latest",
        source="github",
        source_url=repo.get("html_url", ""),
        author=repo.get("owner", {}).get("login"),
        tags=tags,
        stars=repo.get("stargazers_count", 0),
    )


class GitHubSource(SkillSource):

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            exact_q = f"{query} in:name"
            broad_q = f"{query} claude skill plugin mcp in:name,description,topics"

            exact_items, broad_items = await asyncio.gather(
                _search_github(client, exact_q, per_page=5),
                _search_github(client, broad_q, per_page=10),
            )

            seen: set[str] = set()
            merged: list[SkillPackage] = []

            for repo in exact_items + broad_items:
                full_name = repo.get("full_name", "")
                if full_name in seen:
                    continue
                seen.add(full_name)
                merged.append(_repo_to_package(repo))

            merged.sort(key=lambda p: p.stars or 0, reverse=True)

            top_stars = merged[0].stars if merged else 0
            if top_stars < 1000 and len(query) >= 3:
                fuzzy_items = await _search_github(client, query, per_page=5)
                for repo in fuzzy_items:
                    full_name = repo.get("full_name", "")
                    stars = repo.get("stargazers_count", 0)
                    name = repo.get("name", "")
                    if full_name not in seen and stars >= 1000 and _is_similar(query, name):
                        pkg = _repo_to_package(repo)
                        pkg.description = f"你要找的是不是这个？ — {pkg.description}"
                        pkg.tags = ["suggestion"] + pkg.tags
                        merged.insert(0, pkg)
                        break

        return merged[:5]

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub install uses marketplace clone flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
