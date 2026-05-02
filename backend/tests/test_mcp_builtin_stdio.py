"""Tests for Brave + Tavily stdio builtins."""
import os
import pytest
from app.services.mcp_service import MCPService, _BUILTIN_MCP_SERVERS


def test_brave_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "brave-search" in names


def test_tavily_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "tavily" in names


def test_register_skips_brave_if_no_key(db, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="brave-search").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    assert db.query(McpServer).filter_by(name="brave-search").first() is None


def test_register_creates_brave_if_key_set(db, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key-123")
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="brave-search").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    row = db.query(McpServer).filter_by(name="brave-search").first()
    assert row is not None
    assert row.scope == "system"
    assert "BRAVE_API_KEY" in row.env
    assert row.env["BRAVE_API_KEY"] == "test-key-123"
