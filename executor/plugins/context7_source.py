"""Context7 SkillSource — search Context7's library catalog for documentation resources.

Uses Context7 public API (https://context7.com/api/v2/libs/search).
Returns libraries with up-to-date documentation as search results.
"""
from __future__ import annotations

import logging

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_C7_SEARCH_URL = "https://context7.com/api/v2/libs/search"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class Context7Source(SkillSource):

    @property
    def source_name(self) -> str:
        return "context7"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _C7_SEARCH_URL,
                    params={"libraryName": query, "query": query},
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 429:
                    logger.warning("Context7 rate limited")
                    return []
                if resp.status_code != 200:
                    logger.warning("Context7 search returned %d", resp.status_code)
                    return []
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Context7 search failed: %s", exc)
            return []

        items = data if isinstance(data, list) else data.get("results", data.get("items", []))

        results: list[SkillPackage] = []
        for lib in items[:5]:
            lib_id = lib.get("id", "")
            name = lib.get("title") or lib_id.split("/")[-1] if lib_id else ""
            desc = lib.get("description") or ""
            stars = lib.get("stars") or 0
            snippets = lib.get("totalSnippets") or 0
            trust = lib.get("trustScore") or 0

            results.append(SkillPackage(
                name=name,
                description=f"{desc} ({snippets} code snippets, trust: {trust}/10)",
                version=lib.get("versions", ["latest"])[0] if lib.get("versions") else "latest",
                source="context7",
                source_url=f"https://context7.com{lib_id}" if lib_id.startswith("/") else "",
                author=lib_id.split("/")[1] if lib_id.count("/") >= 2 else None,
                tags=["docs", f"{snippets} snippets"],
                stars=stars,
            ))

        results.sort(key=lambda p: p.stars or 0, reverse=True)
        return results[:3]

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("Context7 libraries are documentation, not installable skills")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
