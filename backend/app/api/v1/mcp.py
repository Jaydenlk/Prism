"""
Prism v2 — MCP Server API Endpoints (DOC-09 Task 9.1)

All routes require authentication (current user from Bearer JWT).
scope-based permission is enforced in MCPService — no extra dependency needed.

Routes (all under /api/v1):
  GET    /mcp-servers                  — list system + user MCP Servers
  POST   /mcp-servers                  — create user-scoped MCP Server
  DELETE /mcp-servers/{server_id}      — delete user-scoped MCP Server
  POST   /mcp-servers/{server_id}/test — test server connectivity (capabilities stub)

  POST   /mcp-installs                 — install MCP Server for current user
  GET    /mcp-installs                 — list current user's installs
  PATCH  /mcp-installs/{install_id}    — update is_enabled / config_override
  DELETE /mcp-installs/{install_id}    — uninstall (remove link)

ADR-010 pattern (from Task 2.3):
  scope=system: read by everyone, not deletable by regular users
  scope=user:   read/write/delete only by owner (铁律 4)
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.mcp import (
    InstallMCPRequest,
    MCPInstallResponse,
    McpServerCreate,
    McpServerResponse,
    UpdateMCPInstallRequest,
)
from app.services.mcp_service import MCPService

import structlog
logger = structlog.get_logger()

router = APIRouter(tags=["mcp"])


# ---------------------------------------------------------------------------
# MCP Server CRUD
# ---------------------------------------------------------------------------


@router.get("/mcp-servers", response_model=ApiResponse[list[McpServerResponse]])
def list_mcp_servers(
    include_system: bool = True,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[list[McpServerResponse]]:
    """List all MCP Servers visible to the current user.

    Returns system-scope (built-ins) plus the user's own custom servers.
    """
    svc = MCPService(db)
    servers = svc.list_servers(user_id=str(current_user.id), include_system=include_system)
    return ApiResponse(data=servers)


@router.post(
    "/mcp-servers",
    response_model=ApiResponse[McpServerResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_mcp_server(
    data: McpServerCreate,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[McpServerResponse]:
    """Create a new user-scoped MCP Server configuration.

    The ``scope`` is always forced to 'user' — system servers are bootstrapped
    in lifespan only.
    """
    svc = MCPService(db)
    server = svc.create_server(user_id=str(current_user.id), data=data)
    return ApiResponse(data=server)


@router.get("/mcp-servers/{server_id}", response_model=ApiResponse)
def get_mcp_server(
    server_id: str,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse:
    """Fetch a single MCP Server by ID (system or user-owned)."""
    svc = MCPService(db)
    server = svc.get_server(server_id=server_id, user_id=str(current_user.id))
    return ApiResponse(data=server)


@router.delete(
    "/mcp-servers/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_mcp_server(
    server_id: str,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> None:
    """Delete a user-scoped MCP Server.

    Raises 403 if the server is system-scoped or not owned by the current user.
    """
    svc = MCPService(db)
    svc.delete_server(server_id=server_id, user_id=str(current_user.id))


@router.post("/mcp-servers/{server_id}/test", status_code=200)
async def test_mcp_server(
    server_id: str,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, Any]:
    """Real connection test: transient MCPClient, 10s timeout.

    Enforces user ownership: system-scope readable to all, user-scope owner-only.
    """
    return await MCPService(db).test_server(
        server_id=server_id, user_id=str(current_user.id)
    )


# ---------------------------------------------------------------------------
# MCP Install CRUD (user_mcp_installs)
# ---------------------------------------------------------------------------


@router.post(
    "/mcp-installs",
    response_model=ApiResponse[MCPInstallResponse],
    status_code=status.HTTP_201_CREATED,
)
def install_mcp_server(
    data: InstallMCPRequest,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[MCPInstallResponse]:
    """Install an MCP Server for the current user.

    Creates a user_mcp_installs row. Raises 409 if already installed.
    """
    svc = MCPService(db)
    install = svc.install(user_id=str(current_user.id), data=data)
    return ApiResponse(data=install)


@router.get("/mcp-installs", response_model=ApiResponse[list[MCPInstallResponse]])
def list_mcp_installs(
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[list[MCPInstallResponse]]:
    """List all MCP Servers installed by the current user (enabled + disabled)."""
    svc = MCPService(db)
    installs = svc.list_installs(user_id=str(current_user.id))
    return ApiResponse(data=installs)


@router.patch(
    "/mcp-installs/{install_id}",
    response_model=ApiResponse[MCPInstallResponse],
)
def update_mcp_install(
    install_id: str,
    data: UpdateMCPInstallRequest,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[MCPInstallResponse]:
    """Update is_enabled or config_override for an existing MCP install."""
    svc = MCPService(db)
    install = svc.update_install(
        user_id=str(current_user.id),
        install_id=install_id,
        data=data,
    )
    return ApiResponse(data=install)


@router.delete(
    "/mcp-installs/{install_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def uninstall_mcp_server(
    install_id: str,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> None:
    """Uninstall (remove) the current user's link to an MCP Server."""
    svc = MCPService(db)
    svc.uninstall(user_id=str(current_user.id), install_id=install_id)
