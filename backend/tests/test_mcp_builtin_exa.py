"""Tests for exa HTTP builtin entry."""
import os
import pytest
from app.services.mcp_service import MCPService, _BUILTIN_MCP_SERVERS


def test_exa_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "exa" in names
    exa = next(s for s in _BUILTIN_MCP_SERVERS if s["name"] == "exa")
    assert exa["transport"] == "http"
    assert exa["url"] == "https://mcp.exa.ai/mcp"


def test_register_skips_exa_if_no_key(db, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="exa").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    assert db.query(McpServer).filter_by(name="exa").first() is None


def test_register_creates_exa_with_encrypted_headers(db, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key-xyz")
    from app.models.mcp_server import McpServer
    from app.core.security import decrypt_value
    from app.core.config import settings
    import json
    db.query(McpServer).filter_by(name="exa").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    row = db.query(McpServer).filter_by(name="exa").first()
    assert row is not None
    assert row.transport == "http"
    assert row.url == "https://mcp.exa.ai/mcp"
    assert row.headers_encrypted is not None
    plaintext = decrypt_value(row.headers_encrypted, settings.ENCRYPTION_KEY)
    headers = json.loads(plaintext)
    assert headers["Authorization"] == "Bearer exa-test-key-xyz"
    assert headers["Content-Type"] == "application/json"
