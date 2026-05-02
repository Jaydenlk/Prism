"""Tests for executor __main__ Step 3d plugin bootstrap section."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_bootstrap_fetches_skills_and_mcp_servers(monkeypatch):
    """Bootstrap function calls both internal endpoints with CALLBACK_SECRET."""
    monkeypatch.setenv("CALLBACK_SECRET", "test-secret-abc")

    fake_skills = [{"skill_name": "git-helper", "install_path": "/data/.prism/skills/@local/git-helper", "source": "local", "source_url": None, "version": "1.0"}]
    fake_servers = [{"id": "s1", "name": "exa", "scope": "system", "transport": "http", "url": "https://mcp.exa.ai/mcp", "headers": {"Authorization": "Bearer x"}}]

    fake_resp_skills = MagicMock(); fake_resp_skills.json = MagicMock(return_value={"skills": fake_skills}); fake_resp_skills.raise_for_status = MagicMock()
    fake_resp_servers = MagicMock(); fake_resp_servers.json = MagicMock(return_value={"servers": fake_servers}); fake_resp_servers.raise_for_status = MagicMock()

    fake_http = AsyncMock()
    fake_http.get = AsyncMock(side_effect=[fake_resp_skills, fake_resp_servers])

    from executor.__main__ import bootstrap_plugins
    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = fake_http
        skills, servers = await bootstrap_plugins(
            backend_url="http://backend:8000",
            user_id="user-uuid-1",
            callback_secret="test-secret-abc",
        )
    assert skills == fake_skills
    assert servers == fake_servers


@pytest.mark.asyncio
async def test_bootstrap_failure_returns_empty_not_crash():
    """If backend unreachable, log warning + return ([], []) — don't crash."""
    import structlog.testing
    from executor.__main__ import bootstrap_plugins
    fake_http = AsyncMock()
    fake_http.get = AsyncMock(side_effect=Exception("connection refused"))
    with structlog.testing.capture_logs() as log_entries:
        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = fake_http
            skills, servers = await bootstrap_plugins(
                backend_url="http://backend:8000",
                user_id="user-uuid-1",
                callback_secret="x",
            )
    assert skills == []
    assert servers == []
    assert any("plugin_bootstrap_failed" in e.get("event", "") for e in log_entries)
