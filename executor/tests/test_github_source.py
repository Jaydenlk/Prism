"""GitHub SkillSource adapter tests."""
from __future__ import annotations

import pytest
import respx
import httpx

from executor.plugins.github_source import GitHubSource, _GITHUB_REPOS_URL


@pytest.fixture
def source():
    return GitHubSource()


class TestGitHubSourceSearch:

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_skill_packages(self, source):
        respx.get(_GITHUB_REPOS_URL).mock(return_value=httpx.Response(200, json={
            "items": [{
                "name": "weather-skill",
                "full_name": "owner/weather-skill",
                "description": "A weather lookup skill",
                "html_url": "https://github.com/owner/weather-skill",
                "stargazers_count": 42,
                "topics": ["skill", "weather"],
                "owner": {"login": "owner"},
            }]
        }))
        results = await source.search("weather")
        assert len(results) == 1
        assert results[0].name == "weather-skill"
        assert results[0].source == "github"
        assert results[0].source_url == "https://github.com/owner/weather-skill"
        assert results[0].author == "owner"

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, source):
        results = await source.search("")
        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, source):
        respx.get(_GITHUB_REPOS_URL).mock(return_value=httpx.Response(403))
        results = await source.search("test")
        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_multiple_results(self, source):
        respx.get(_GITHUB_REPOS_URL).mock(return_value=httpx.Response(200, json={
            "items": [
                {"name": "a", "full_name": "x/a", "description": "", "html_url": "https://github.com/x/a", "owner": {"login": "x"}, "topics": []},
                {"name": "b", "full_name": "y/b", "description": "", "html_url": "https://github.com/y/b", "owner": {"login": "y"}, "topics": []},
            ]
        }))
        results = await source.search("test")
        assert len(results) == 2
        assert results[0].name == "a"
        assert results[1].name == "b"
