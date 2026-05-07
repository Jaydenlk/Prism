"""GitHub SkillSource adapter tests."""
from __future__ import annotations

import pytest
import respx
import httpx

from executor.plugins.github_source import GitHubSource, _GITHUB_SEARCH_URL


@pytest.fixture
def source():
    return GitHubSource()


class TestGitHubSourceSearch:

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_skill_packages(self, source):
        respx.get(_GITHUB_SEARCH_URL).mock(return_value=httpx.Response(200, json={
            "items": [{
                "repository": {
                    "full_name": "owner/repo",
                    "description": "A useful skill",
                    "html_url": "https://github.com/owner/repo",
                    "topics": ["skill", "ai"],
                    "owner": {"login": "owner"},
                },
                "path": "skills/my-skill/SKILL.md",
            }]
        }))
        results = await source.search("useful")
        assert len(results) == 1
        assert results[0].name == "my-skill"
        assert results[0].source == "github"
        assert "github.com/owner/repo" in results[0].source_url
        assert results[0].author == "owner"

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, source):
        results = await source.search("")
        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, source):
        respx.get(_GITHUB_SEARCH_URL).mock(return_value=httpx.Response(403))
        results = await source.search("test")
        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_deduplicates_same_repo(self, source):
        respx.get(_GITHUB_SEARCH_URL).mock(return_value=httpx.Response(200, json={
            "items": [
                {"repository": {"full_name": "a/b", "description": "", "html_url": "https://github.com/a/b", "owner": {"login": "a"}}, "path": "skills/s1/SKILL.md"},
                {"repository": {"full_name": "a/b", "description": "", "html_url": "https://github.com/a/b", "owner": {"login": "a"}}, "path": "skills/s2/SKILL.md"},
            ]
        }))
        results = await source.search("test")
        assert len(results) == 1
