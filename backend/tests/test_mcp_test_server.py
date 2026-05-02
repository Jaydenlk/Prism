"""Tests for MCPService.test_server real connection (Task 2 / L3)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from app.services.mcp_service import MCPService

DUMMY_USER = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_test_server_stdio_success(db):
    """Stdio MCP: start() succeeds → list_tools → success dict."""
    from app.models.mcp_server import McpServer

    server = McpServer(
        name="echo-test", scope="system", command="echo", args=["{}"], env={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    fake_client = MagicMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[{"name": "search"}, {"name": "fetch"}])
    fake_client.stop = AsyncMock(return_value=None)

    with patch("app.services.mcp_service.MCPClient", return_value=fake_client):
        result = await MCPService(db).test_server(server.id, user_id=DUMMY_USER)

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
        result = await MCPService(db).test_server(server.id, user_id=DUMMY_USER)

    assert result["success"] is False
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_test_server_http_with_real_branch(db):
    """HTTP transport: MCPClient(transport='http') is constructed with decrypted headers."""
    import json
    from app.core.config import settings
    from app.core.security import encrypt_value
    from app.models.mcp_server import McpServer

    headers = {"Authorization": "Bearer test", "Content-Type": "application/json"}
    server = McpServer(
        name="http-test", scope="system", command="__http__", args=[], env={},
        transport="http", url="https://mcp.example.test/mcp",
        headers_encrypted=encrypt_value(json.dumps(headers), settings.ENCRYPTION_KEY),
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    fake_client = MagicMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[{"name": "web_search_exa"}])
    fake_client.stop = AsyncMock(return_value=None)

    with patch("app.services.mcp_service.MCPClient", return_value=fake_client) as MockClient:
        result = await MCPService(db).test_server(server.id, user_id=DUMMY_USER)

    assert result["success"] is True
    assert result["tools"] == ["web_search_exa"]
    # Verify HTTP transport branch wired correctly
    kwargs = MockClient.call_args.kwargs
    assert kwargs["transport"] == "http"
    assert kwargs["url"] == "https://mcp.example.test/mcp"
    assert kwargs["headers"]["Authorization"] == "Bearer test"


@pytest.mark.asyncio
async def test_test_server_unknown_id(db):
    """Unknown server_id returns success=False with 'not found' error."""
    result = await MCPService(db).test_server(
        "00000000-0000-0000-0000-000000000000", user_id=DUMMY_USER
    )
    assert result["success"] is False
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_test_server_user_scope_403_for_other_user(db):
    """Security: user-scope server cannot be tested by a different user (铁律 4)."""
    from app.models.user import User
    from app.models.mcp_server import McpServer

    owner = User(
        email="owner@test.local", username="owner_unique", password_hash="x", role="user",
    )
    db.add(owner)
    db.flush()

    server = McpServer(
        name="private-stdio", scope="user", user_id=owner.id,
        command="echo", args=[], env={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(server)
    db.commit()

    other_user_id = "00000000-0000-0000-0000-0000000000ff"
    with pytest.raises(HTTPException) as exc:
        await MCPService(db).test_server(server.id, user_id=other_user_id)
    assert exc.value.status_code == 403
