"""Tests for MCPService.test_server real connection (Task 2 / L3)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.mcp_service import MCPService


@pytest.mark.asyncio
async def test_test_server_stdio_success(db):
    """Stdio MCP: start() succeeds → get_tool_definitions → success dict."""
    from app.models.mcp_server import McpServer

    server = McpServer(
        name="echo-test", scope="system", command="echo", args=["{}"], env={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    fake_client = MagicMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.get_tool_definitions = MagicMock(
        return_value=[{"name": "search"}, {"name": "fetch"}]
    )
    fake_client.stop = AsyncMock(return_value=None)

    with patch("app.services.mcp_service.MCPClient", return_value=fake_client):
        result = await MCPService(db).test_server(server.id)

    assert result["success"] is True
    assert set(result["tools"]) == {"search", "fetch"}
    assert result["error"] is None
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_test_server_stdio_timeout(db):
    """Stdio MCP that hangs → 10s timeout → success=False with timeout message."""
    from app.models.mcp_server import McpServer

    server = McpServer(
        name="hang-test", scope="system", command="sleep", args=["100"], env={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    import asyncio

    async def hang():
        await asyncio.sleep(60)

    fake_client = MagicMock()
    fake_client.start = hang
    fake_client.stop = AsyncMock(return_value=None)

    with patch("app.services.mcp_service.MCPClient", return_value=fake_client):
        result = await MCPService(db).test_server(server.id)

    assert result["success"] is False
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_test_server_http_pending(db):
    """HTTP transport returns graceful failure until Task 5 lands."""
    from app.models.mcp_server import McpServer

    server = McpServer(
        name="http-test", scope="system", command="__http__", args=[], env={},
        transport="http", url="https://mcp.example.test/mcp", headers_encrypted=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    result = await MCPService(db).test_server(server.id)

    assert result["success"] is False
    assert "http" in result["error"].lower()


@pytest.mark.asyncio
async def test_test_server_unknown_id(db):
    """Unknown server_id returns success=False with 'not found' error."""
    result = await MCPService(db).test_server("00000000-0000-0000-0000-000000000000")
    assert result["success"] is False
    assert "not found" in result["error"].lower()
