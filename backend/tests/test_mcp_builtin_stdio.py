"""Tests for SearXNG + Tavily stdio builtins."""
import os
import pytest
from app.services.mcp_service import MCPService, _BUILTIN_MCP_SERVERS


def test_searxng_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "searxng" in names


def test_tavily_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "tavily" in names


def test_register_creates_searxng_unconditionally(db):
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="searxng").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    row = db.query(McpServer).filter_by(name="searxng").first()
    assert row is not None
    assert row.scope == "system"
    assert row.env == {"SEARXNG_URL": "http://searxng:8080"}
