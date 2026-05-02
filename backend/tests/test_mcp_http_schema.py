"""Tests for MCP HTTP transport schema additions."""
import pytest
from pydantic import ValidationError
from app.schemas.mcp import McpServerCreate, McpServerResponse


def test_create_stdio_requires_command():
    with pytest.raises(ValidationError):
        McpServerCreate(name="x", transport="stdio", url=None)


def test_create_http_requires_url():
    with pytest.raises(ValidationError):
        McpServerCreate(name="x", transport="http", command="__http__")


def test_create_http_with_url_ok():
    m = McpServerCreate(
        name="x", transport="http", url="https://mcp.example/mcp",
        command="__http__", args=[], env={},
        headers={"Authorization": "Bearer abc"},
    )
    assert m.transport == "http"


def test_response_masks_authorization():
    from datetime import datetime, timezone
    r = McpServerResponse(
        id="00000000-0000-0000-0000-000000000000",
        name="x", scope="system", transport="http",
        url="https://example/mcp", command="__http__",
        args=[], env={},
        headers={"Authorization": "Bearer secret-abc-123", "Content-Type": "application/json"},
        created_at=datetime.now(timezone.utc),
    )
    d = r.model_dump()
    assert d["headers"]["Authorization"] == "Bearer ***"
    assert d["headers"]["Content-Type"] == "application/json"  # non-sensitive unchanged
