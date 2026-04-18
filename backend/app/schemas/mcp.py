"""
Prism v2 — MCP Server Pydantic Schemas (DOC-09 Task 9.1)

Schema map:
  CreateMCPServerRequest  — POST /mcp-servers (user-created, scope=user)
  MCPServerResponse       — GET  /mcp-servers item
  InstallMCPRequest       — POST /mcp-installs
  MCPInstallResponse      — install list item (includes JOIN mcp_servers.name)
  UpdateMCPInstallRequest — PATCH /mcp-installs/{id}
  MCPTestResponse         — POST /mcp-servers/{id}/test
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MCP Server schemas
# ---------------------------------------------------------------------------


class CreateMCPServerRequest(BaseModel):
    """Request body for creating a user-scoped MCP Server configuration."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    command: str = Field(..., min_length=1, max_length=500)
    args: list[str] = []
    env: dict[str, str] = {}


class MCPServerResponse(BaseModel):
    """Response representation of a single MCP Server.

    ``scope`` is either 'system' (built-in, undeletable) or 'user'.
    ``env`` values for system-scope servers are masked (returned as '***')
    to prevent leaking credentials embedded in system config.
    """

    id: str
    name: str
    description: str | None
    scope: str                      # 'system' | 'user'
    command: str
    args: list[str]
    env: dict[str, Any]            # system scope env values masked
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# MCP Install schemas
# ---------------------------------------------------------------------------


class InstallMCPRequest(BaseModel):
    """Request body for installing (linking) an MCP Server for the current user."""

    mcp_server_id: str
    config_override: dict[str, Any] = {}


class MCPInstallResponse(BaseModel):
    """Response representation of a user's MCP Server install record."""

    id: str
    mcp_server_id: str
    mcp_server_name: str            # denormalised from JOIN
    is_enabled: bool
    config_override: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateMCPInstallRequest(BaseModel):
    """PATCH body — at least one field must be provided."""

    is_enabled: bool | None = None
    config_override: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Test / capabilities
# ---------------------------------------------------------------------------


class MCPTestResponse(BaseModel):
    """Result of POST /mcp-servers/{id}/test (capabilities stub)."""

    success: bool
    server_id: str
    detected_capabilities: list[str] = []   # e.g. ["tools", "resources", "prompts"]
    error: str | None = None
