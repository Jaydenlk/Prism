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
layer (MCPServerResponse), never in the DB.

ADR compliance:
  -铁律 4: all list/delete/install/uninstall methods accept user_id and filter
  - system scope: undeletable by regular user (403)
  - user_mcp_installs UNIQUE(user_id, mcp_server_id) enforced at DB level
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mcp_server import McpServer, UserMcpInstall
from app.schemas.mcp import (
    CreateMCPServerRequest,
    InstallMCPRequest,
    MCPInstallResponse,
    MCPServerResponse,
    MCPTestResponse,
    UpdateMCPInstallRequest,
)

if TYPE_CHECKING:
    pass

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
    ) -> list[MCPServerResponse]:
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
        data: CreateMCPServerRequest,
    ) -> MCPServerResponse:
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

    def test_server(self, server_id: str, user_id: str) -> MCPTestResponse:
        """Capability-detection stub for POST /mcp-servers/{id}/test.

        Phase 1: synchronous stub — always returns success=True with a
        placeholder capabilities list. Full async probing (stdio/SSE launch)
        is deferred to DOC-05 MCPClient integration.
        """
        server = self._db.get(McpServer, server_id)
        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"MCP Server {server_id} not found.",
            )
        self._assert_readable(server, user_id)

        # Stub: report the standard MCP protocol capability set
        detected = ["tools"]
        logger.info(
            "mcp_server.test_stub",
            server_id=server_id,
            detected=detected,
        )
        return MCPTestResponse(
            success=True,
            server_id=server_id,
            detected_capabilities=detected,
        )

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
        """Register or refresh _BUILTIN_MCP_SERVERS, skipping entries whose env var is unset."""
        import os
        for spec in _BUILTIN_MCP_SERVERS:
            env_var = spec.get("env_var")
            if env_var:
                api_key = os.environ.get(env_var)
                if not api_key:
                    logger.info("mcp.builtin.skipped", name=spec["name"], reason=f"{env_var} not set")
                    continue
                env = {env_var: api_key}
            else:
                env = {}
            existing = self._db.query(McpServer).filter_by(name=spec["name"], scope="system").first()
            if existing:
                existing.env = env
                self._db.commit()
                continue
            row = McpServer(
                name=spec["name"],
                description=spec.get("description"),
                scope="system",
                command=spec["command"],
                args=spec.get("args", []),
                env=env,
                created_at=datetime.now(timezone.utc),
            )
            self._db.add(row)
            self._db.commit()
            logger.info("mcp.builtin.registered", name=spec["name"])

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
    def _to_server_response(server: McpServer) -> MCPServerResponse:
        """Convert McpServer ORM to response schema.

        system scope env values are masked to '***' to prevent secret leakage.
        user scope env is returned as-is.
        """
        env: dict
        if server.scope == "system" and server.env:
            env = {k: "***" for k in server.env}
        else:
            env = server.env or {}

        return MCPServerResponse(
            id=server.id,
            name=server.name,
            description=server.description,
            scope=server.scope,
            command=server.command,
            args=server.args or [],
            env=env,
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
