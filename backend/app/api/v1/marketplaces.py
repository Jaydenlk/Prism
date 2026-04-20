"""
Prism v2 — Skills Marketplace API (DOC-SK R1, ADR-086)

Claude Code plugin marketplace registration. Each registered marketplace caches
its `.claude-plugin/marketplace.json` catalog; users browse the catalog and
install plugins (v1: plugin = single skill wrapper) via /skills/install.

Endpoints (all under /api/v1/marketplaces, admin-authenticated):
  GET    /                   — list registered marketplaces
  POST   /                   — register a new marketplace (body: {url, name})
  DELETE /{id}               — unregister (cascades skill_installs.marketplace_id → NULL)
  POST   /{id}/sync          — force refresh the catalog
  POST   /{id}/plugins/{name}/install — Session 4c 5-source install (ADR-090)
"""
from __future__ import annotations

import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.marketplace import MarketplaceRegistry
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.marketplace import (
    InstallReport,
    MarketplaceCreate,
    MarketplaceResponse,
)
from app.services.marketplace_service import MarketplaceService

logger = structlog.get_logger()
router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


def _to_response(entry: MarketplaceRegistry) -> MarketplaceResponse:
    catalog = entry.catalog_json or None
    plugin_count = 0
    if isinstance(catalog, dict):
        plugins = catalog.get("plugins")
        if isinstance(plugins, list):
            plugin_count = len(plugins)
    return MarketplaceResponse(
        id=entry.id,
        url=entry.url,
        name=entry.name,
        catalog_json=catalog,
        plugin_count=plugin_count,
        last_fetched_at=(
            entry.last_fetched_at.isoformat() if entry.last_fetched_at else None
        ),
        created_by=entry.created_by,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
    )


@router.get(
    "",
    response_model=ApiResponse[list[MarketplaceResponse]],
    summary="List registered marketplaces",
)
async def list_marketplaces(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[MarketplaceResponse]]:
    svc = MarketplaceService(db=db)
    entries = svc.list_all(user_id=current_user.id)
    return ApiResponse(data=[_to_response(e) for e in entries])


@router.post(
    "",
    response_model=ApiResponse[MarketplaceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new marketplace (fetches catalog best-effort)",
)
async def create_marketplace(
    request: MarketplaceCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[MarketplaceResponse]:
    svc = MarketplaceService(db=db)
    try:
        # Session 4c ADR-090: svc.create may clone a git repo (120s timeout)
        # via blocking subprocess. Run in threadpool to avoid blocking the
        # FastAPI event loop.
        entry = await asyncio.to_thread(
            svc.create,
            user_id=current_user.id,
            url=str(request.url),
            name=request.name,
        )
    except Exception as exc:
        # Unique violation on url = already registered. Fall through to DB layer to surface it.
        logger.warning(
            "marketplaces_api.create_error", url=str(request.url), error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to register marketplace: {exc}",
        )
    return ApiResponse(data=_to_response(entry))


@router.delete(
    "/{marketplace_id}",
    response_model=ApiResponse[dict],
    summary="Unregister a marketplace (sets linked skill_installs.marketplace_id to NULL)",
)
async def delete_marketplace(
    marketplace_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    svc = MarketplaceService(db=db)
    removed = svc.delete(marketplace_id=marketplace_id, user_id=current_user.id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace not found",
        )
    return ApiResponse(data={"id": marketplace_id, "deleted": True})


@router.post(
    "/{marketplace_id}/sync",
    response_model=ApiResponse[MarketplaceResponse],
    summary="Force refresh the marketplace catalog",
)
async def sync_marketplace(
    marketplace_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[MarketplaceResponse]:
    svc = MarketplaceService(db=db)
    # Session 4c ADR-090: svc.sync may re-clone a git repo (120s timeout).
    # Run in threadpool to avoid blocking the FastAPI event loop.
    entry = await asyncio.to_thread(
        svc.sync, marketplace_id=marketplace_id, user_id=current_user.id
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace not found",
        )
    return ApiResponse(data=_to_response(entry))


@router.post(
    "/{marketplace_id}/plugins/{plugin_name}/install",
    response_model=ApiResponse[InstallReport],
    status_code=status.HTTP_201_CREATED,
    summary="Install a plugin from marketplace catalog (Session 4c, ADR-090)",
)
async def install_plugin_from_marketplace(
    marketplace_id: str,
    plugin_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[InstallReport]:
    """Install a plugin from a registered marketplace catalog.

    Dispatches to one of 5 source resolvers (relative / github / url /
    git-subdir / npm) per the plugin entry's `source` field. Downloads plugin
    package to /app/data/plugin_cache/, parses each skills/<name>/SKILL.md,
    UPSERTs skill_installs rows with source='marketplace' + marketplace_id FK.

    Errors: 404 marketplace/plugin not found; 409 concurrent install; 422
    download failed / plugin has no skills; 504 download timeout.
    """
    svc = MarketplaceService(db=db)
    report = await svc.install_plugin(
        marketplace_id=marketplace_id,
        plugin_name=plugin_name,
        user_id=current_user.id,
    )
    return ApiResponse(data=report)
