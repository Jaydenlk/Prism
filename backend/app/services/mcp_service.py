"""
Prism v2 — MCP Server Configuration Service (DOC-09 Task 9.1)

Responsibilities:
  - CRUD for mcp_servers table (system built-ins + user-custom)
  - Per-user install / uninstall / toggle via user_mcp_installs table
  - Lifespan bootstrap of system-scoped built-in MCP Servers

scope rules (align with Task 2.3 Provider scope pattern):
  system:  built-in, all users can see, only admin can delete (guard in API layer)
           → not deletable by regular users (403 enforced here)
  user:    user-defined, owner-only visible and mutable
           → create_server() always forces scope='user'

Credentials in env are NOT additionally encrypted for MCP (env values are
plain-text in the DB for now — user manages secrets via config_override).
Sensitive system-scope env values are masked at the *schema* serialisation
layer (McpServerResponse), never in the DB.

ADR compliance:
  -铁律 4: all list/delete/install/uninstall methods accept user_id and filter
  - system scope: undeletable by regular user (403)
  - user_mcp_installs UNIQUE(user_id, mcp_server_id) enforced at DB level
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value


_ENV_VAR_PATTERN = re.compile(r"\$\{env:(\w+)\}")


def _expand_env_vars(text: str) -> str:
    """Substitute `${env:VAR_NAME}` with os.environ.get('VAR_NAME', '')."""
    return _ENV_VAR_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), text)


def _decrypt_headers(ciphertext: str | None) -> dict[str, str]:
    """Decrypt headers_encrypted ciphertext (AES-256-GCM JSON envelope) → plaintext dict.

    Returns {} when ciphertext is None / empty (e.g., stdio rows).
    """
    if not ciphertext:
        return {}
    return json.loads(decrypt_value(ciphertext, settings.ENCRYPTION_KEY))

from app.models.mcp_server import McpServer, UserMcpInstall
from app.schemas.mcp import (
    InstallMCPRequest,
    MCPInstallResponse,
    McpServerCreate,
    McpServerResponse,
    UpdateMCPInstallRequest,
)
from executor.plugins.mcp_client import MCPClient

import structlog
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Built-in system MCP Servers
# ---------------------------------------------------------------------------

_BUILTIN_MCP_SERVERS: list[dict] = [
    {
        "name": "web_search",
        "description": "网页搜索 — Anthropic MCP Web Search",
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-web-search"],
    },
    {
        "name": "filesystem",
        "description": "文件系统访问 — 读写本地文件",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
    },
    {
        "name": "brave-search",
        "description": "Brave Search MCP — independent web index with 2000 free queries/month.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_var": "BRAVE_API_KEY",
    },
    {
        "name": "tavily",
        "description": "Tavily AI Search MCP — agentic search with 1000 free queries/month.",
        "command": "npx",
        "args": ["-y", "tavily-mcp@latest"],
        "env_var": "TAVILY_API_KEY",
    },
    {
        "name": "exa",
        "description": "Exa AI 搜索 — 神经网络驱动的语义搜索 + URL 内容提取（HTTP transport）。",
        "transport": "http",
        "url": "https://mcp.exa.ai/mcp",
        "headers_template": {
            "Authorization": "Bearer ${env:EXA_API_KEY}",
            "Content-Type": "application/json",
        },
        "env_var": "EXA_API_KEY",
    },
]


# ---------------------------------------------------------------------------
# MCPService
# ---------------------------------------------------------------------------


class MCPService:
    """MCP Server configuration management (DOC-09 Task 9.1)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Server-level operations
    # ------------------------------------------------------------------

    def list_servers(
        self,
        user_id: str,
        include_system: bool = True,
    ) -> list[McpServerResponse]:
        """List MCP Servers visible to this user.

        Returns system-scope (if include_system=True) UNION user's own servers.
        铁律 4: user-scope rows filtered to user_id.
        """
        from sqlalchemy import or_

        query = self._db.query(McpServer)
        if include_system:
            query = query.filter(
                or_(
                    McpServer.scope == "system",
                    (McpServer.scope == "user"),  # further filtered below
                )
            )
            # System rows are always visible; user rows only for owner.
            # Rebuild with explicit OR to avoid double-returning system rows.
            rows = (
                self._db.query(McpServer)
                .filter(
                    or_(
                        McpServer.scope == "system",
                        (McpServer.scope == "user"),
                    )
                )
                .all()
            )
            # Post-filter user-scope to owner only (铁律 4)
            rows = [r for r in rows if r.scope == "system" or r.user_id == user_id]
        else:
            rows = (
                self._db.query(McpServer)
                .filter(McpServer.scope == "user", McpServer.user_id == user_id)
                .all()
            )

        return [self._to_server_response(r) for r in rows]

    def get_server(self, server_id: str, user_id: str) -> McpServer:
        """Fetch a single McpServer with access check (铁律 4)."""
        server = self._db.get(McpServer, server_id)
        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"MCP Server {server_id} not found.",
            )
        self._assert_readable(server, user_id)
        return server

    def create_server(
        self,
        user_id: str,
        data: McpServerCreate,
    ) -> McpServerResponse:
        """Create a user-scoped MCP Server configuration.

        scope is always forced to 'user' — system servers are only created
        via register_builtin_servers().
        """
        server = McpServer(
            name=data.name,
            description=data.description,
            scope="user",
            user_id=user_id,
            command=data.command,
            args=data.args,
            env=data.env,
            transport=data.transport,
            url=data.url,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(server)
        self._db.commit()
        self._db.refresh(server)

        logger.info(
            "mcp_server.created",
            server_id=server.id,
            user_id=user_id,
            name=server.name,
        )
        return self._to_server_response(server)

    def delete_server(self, server_id: str, user_id: str) -> None:
        """Delete a user-scoped MCP Server.

        system scope → 403 (undeletable, even by admin via this service layer).
        user scope   → only the owner may delete (铁律 4).
        """
        server = self._db.get(McpServer, server_id)
        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"MCP Server {server_id} not found.",
            )
        if server.scope == "system":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System MCP Servers cannot be deleted.",
            )
        if server.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this MCP Server.",
            )

        self._db.delete(server)
        self._db.commit()

        logger.info(
            "mcp_server.deleted",
            server_id=server_id,
            user_id=user_id,
        )

    async def test_server(self, server_id: str, user_id: str) -> dict[str, Any]:
        """Real connection test: transient MCPClient, list tools, 10s timeout.

        Returns {success, tools, error, latency_ms}.
        Enforces 铁律 4: user must own user-scope server (system-scope readable to all).
        """
        server = self._db.get(McpServer, server_id)
        if server is None:
            return {"success": False, "tools": [], "error": "Server not found", "latency_ms": 0}
        self._assert_readable(server, user_id)

        started = time.monotonic()
        if server.transport == "http":
            headers = _decrypt_headers(server.headers_encrypted)
            client = MCPClient(
                server_name=server.name,
                transport="http",
                url=server.url,
                headers=headers,
            )
        else:
            client = MCPClient(
                server_name=server.name,
                command=server.command,
                args=list(server.args or []),
                env=dict(server.env or {}),
            )

        try:
            await asyncio.wait_for(client.start(), timeout=10.0)
            tools = [t["name"] for t in await client.list_tools()]
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {"success": True, "tools": tools, "error": None, "latency_ms": elapsed_ms}
        except asyncio.TimeoutError:
            return {"success": False, "tools": [], "error": "Connection timeout (10s)", "latency_ms": 10_000}
        except Exception as exc:
            return {"success": False, "tools": [], "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": int((time.monotonic() - started) * 1000)}
        finally:
            try:
                await client.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Install-level operations (user_mcp_installs)
    # ------------------------------------------------------------------

    def list_installs(self, user_id: str) -> list[MCPInstallResponse]:
        """List all MCP Servers installed (enabled/disabled) by this user.

        Performs JOIN with mcp_servers to retrieve server name.
        铁律 4: filtered to user_id.
        """
        rows = (
            self._db.query(UserMcpInstall)
            .filter(UserMcpInstall.user_id == user_id)
            .all()
        )
        return [self._to_install_response(r) for r in rows]

    def install(
        self,
        user_id: str,
        data: InstallMCPRequest,
    ) -> MCPInstallResponse:
        """Install (link) an MCP Server for the current user.

        Verifies the target server exists and is visible to the user.
        UNIQUE(user_id, mcp_server_id) is enforced at DB level — IntegrityError
        is caught and converted to 409.
        """
        # Verify target server exists and is accessible
        self.get_server(data.mcp_server_id, user_id)

        install = UserMcpInstall(
            user_id=user_id,
            mcp_server_id=data.mcp_server_id,
            is_enabled=True,
            config_override=data.config_override,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(install)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="MCP Server is already installed for this user.",
            )
        self._db.refresh(install)

        logger.info(
            "mcp_install.created",
            install_id=install.id,
            user_id=user_id,
            server_id=data.mcp_server_id,
        )
        return self._to_install_response(install)

    def update_install(
        self,
        user_id: str,
        install_id: str,
        data: UpdateMCPInstallRequest,
    ) -> MCPInstallResponse:
        """Update is_enabled or config_override for an existing install.

        铁律 4: only the owning user may update.
        """
        install = self._get_install_owned_by(install_id, user_id)

        if data.is_enabled is not None:
            install.is_enabled = data.is_enabled
        if data.config_override is not None:
            install.config_override = data.config_override

        self._db.commit()
        self._db.refresh(install)

        logger.info(
            "mcp_install.updated",
            install_id=install_id,
            user_id=user_id,
        )
        return self._to_install_response(install)

    def uninstall(self, user_id: str, install_id: str) -> None:
        """Remove the user's link to an MCP Server (physical delete).

        铁律 4: only the owning user may uninstall.
        """
        install = self._get_install_owned_by(install_id, user_id)
        self._db.delete(install)
        self._db.commit()

        logger.info(
            "mcp_install.deleted",
            install_id=install_id,
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Lifespan: register built-in system MCP Servers
    # ------------------------------------------------------------------

    def register_builtin_servers(self) -> None:
        """Register or refresh _BUILTIN_MCP_SERVERS, skipping entries whose env var is unset.

        Single batch fetch of existing system rows + single commit at end (avoid N+1).
        """
        names = [s["name"] for s in _BUILTIN_MCP_SERVERS]
        existing_by_name: dict[str, McpServer] = {
            r.name: r for r in self._db.query(McpServer)
            .filter(McpServer.name.in_(names), McpServer.scope == "system")
            .all()
        }

        any_change = False
        for spec in _BUILTIN_MCP_SERVERS:
            env_var = spec.get("env_var")
            api_key = os.environ.get(env_var) if env_var else None
            if env_var and not api_key:
                logger.info("mcp.builtin.skipped", name=spec["name"], reason=f"{env_var} not set")
                continue

            transport = spec.get("transport", "stdio")
            if transport == "http":
                headers = {k: _expand_env_vars(v) for k, v in spec.get("headers_template", {}).items()}
                row_kwargs: dict[str, Any] = dict(
                    name=spec["name"],
                    description=spec.get("description"),
                    scope="system",
                    command="__http__",
                    args=[],
                    env={},
                    transport="http",
                    url=spec["url"],
                    headers_encrypted=encrypt_value(json.dumps(headers), settings.ENCRYPTION_KEY),
                )
            else:
                row_kwargs = dict(
                    name=spec["name"],
                    description=spec.get("description"),
                    scope="system",
                    command=spec["command"],
                    args=spec.get("args", []),
                    env={env_var: api_key} if env_var else {},
                    transport="stdio",
                    url=None,
                    headers_encrypted=None,
                )

            existing = existing_by_name.get(spec["name"])
            if existing:
                for k, v in row_kwargs.items():
                    setattr(existing, k, v)
            else:
                row_kwargs["created_at"] = datetime.now(timezone.utc)
                self._db.add(McpServer(**row_kwargs))
                logger.info("mcp.builtin.registered", name=spec["name"], transport=transport)
            any_change = True

        if any_change:
            self._db.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_readable(self, server: McpServer, user_id: str) -> None:
        """system scope: anyone can read. user scope: owner only (铁律 4)."""
        if server.scope == "system":
            return
        if server.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this MCP Server.",
            )

    def _get_install_owned_by(self, install_id: str, user_id: str) -> UserMcpInstall:
        """Fetch a UserMcpInstall and verify ownership (铁律 4)."""
        install = self._db.get(UserMcpInstall, install_id)
        if install is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"MCP install {install_id} not found.",
            )
        if install.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this MCP install.",
            )
        return install

    @staticmethod
    def _to_server_response(server: McpServer) -> McpServerResponse:
        """Convert McpServer ORM to response schema.

        system scope env values are masked to '***' to prevent secret leakage.
        headers_encrypted is decrypted inline; validator masks sensitive keys.
        url only populated for http transport.
        """
        env: dict[str, str]
        if server.scope == "system" and server.env:
            env = {k: "***" for k in server.env}
        else:
            env = server.env or {}

        transport = server.transport or "stdio"
        url = server.url if transport == "http" else None
        headers: dict[str, str] | None = None
        if transport == "http" and server.headers_encrypted:
            try:
                headers = _decrypt_headers(server.headers_encrypted)
            except Exception:
                headers = None

        return McpServerResponse(
            id=server.id,
            name=server.name,
            description=server.description,
            scope=server.scope,
            transport=transport,
            command=server.command,
            args=server.args or [],
            env=env,
            url=url,
            headers=headers,
            created_at=server.created_at,
        )

    @staticmethod
    def _to_install_response(install: UserMcpInstall) -> MCPInstallResponse:
        """Convert UserMcpInstall ORM (with eager-loaded mcp_server) to response."""
        return MCPInstallResponse(
            id=install.id,
            mcp_server_id=install.mcp_server_id,
            mcp_server_name=install.mcp_server.name if install.mcp_server else "",
            is_enabled=install.is_enabled,
            config_override=install.config_override or {},
            created_at=install.created_at,
        )
