"""
Prism v2 — MCP Server Pydantic Schemas (DOC-09 Task 9.1)

Schema map:
  CreateMCPServerRequest  — POST /mcp-servers (user-created, scope=user)
  MCPServerResponse       — GET  /mcp-servers item
  InstallMCPRequest       — POST /mcp-installs
  MCPInstallResponse      — install list item (includes JOIN mcp_servers.name)
  UpdateMCPInstallRequest — PATCH /mcp-installs/{id}
  MCPTestResponse         — POST /mcp-servers/{id}/test

  McpServerBase / McpServerCreate / McpServerUpdate / McpServerResponse
    — HTTP transport schema additions (L5a)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


# ---------------------------------------------------------------------------
# HTTP transport schema additions (L5a)
# ---------------------------------------------------------------------------

_SENSITIVE_HEADER_KEYS = {"authorization", "x-api-key", "api-key", "x-auth-token", "cookie"}


class McpServerBase(BaseModel):
    name: str
    description: str | None = None
    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None
    headers: dict[str, str] | None = None


class McpServerCreate(McpServerBase):
    @model_validator(mode="after")
    def _validate_transport_fields(self):
        if self.transport == "stdio":
            if not self.command or self.command == "__http__":
                raise ValueError("stdio transport requires a real command")
        elif self.transport == "http":
            if not self.url:
                raise ValueError("http transport requires url")
            if not self.command:
                self.command = "__http__"
        return self


class McpServerUpdate(McpServerBase):
    name: str | None = None


class McpServerResponse(McpServerBase):
    id: str
    scope: str

    @field_validator("headers")
    @classmethod
    def _mask_sensitive_headers(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return None
        out = {}
        for k, val in v.items():
            if k.lower() in _SENSITIVE_HEADER_KEYS:
                parts = (val or "").split(" ", 1)
                out[k] = f"{parts[0]} ***" if len(parts) == 2 else "***"
            else:
                out[k] = val
        return out
