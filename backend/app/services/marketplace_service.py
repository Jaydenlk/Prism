"""
MarketplaceService — Skills Marketplace registry (DOC-SK R1, ADR-086)

Stores user-registered Claude Code-format marketplaces (`marketplace_registry`
table) and caches their `.claude-plugin/marketplace.json` catalog.

Fetching is best-effort: a registration with an unreachable URL still succeeds
(catalog_json left null, last_fetched_at left null). `sync()` retries the fetch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy.orm import Session

from app.models.marketplace import MarketplaceRegistry

logger = structlog.get_logger()

_FETCH_TIMEOUT_SECONDS = 10.0
_FETCH_MAX_BYTES = 1024 * 1024  # 1 MiB — catalogs are JSON text, not binaries


class MarketplaceService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public CRUD
    # ------------------------------------------------------------------

    def create(self, user_id: str, url: str, name: str) -> MarketplaceRegistry:
        """Insert a marketplace row and attempt an initial catalog fetch.

        Fetch failures are logged but do not fail the registration; call
        `sync()` later to retry.
        """
        catalog, fetched_at = self._try_fetch(url)
        entry = MarketplaceRegistry(
            url=url,
            name=name,
            catalog_json=catalog,
            last_fetched_at=fetched_at,
            created_by=user_id,
        )
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        logger.info(
            "marketplace.create",
            marketplace_id=entry.id,
            url=url,
            name=name,
            user_id=user_id,
            catalog_fetched=catalog is not None,
        )
        return entry

    def list_all(self, user_id: str) -> list[MarketplaceRegistry]:
        """List every registered marketplace the user created."""
        return (
            self._db.query(MarketplaceRegistry)
            .filter(MarketplaceRegistry.created_by == user_id)
            .order_by(MarketplaceRegistry.created_at.desc())
            .all()
        )

    def delete(self, marketplace_id: str, user_id: str) -> bool:
        """Delete a marketplace owned by the user. Returns True if removed."""
        entry = (
            self._db.query(MarketplaceRegistry)
            .filter(
                MarketplaceRegistry.id == marketplace_id,
                MarketplaceRegistry.created_by == user_id,
            )
            .first()
        )
        if entry is None:
            return False
        self._db.delete(entry)
        self._db.commit()
        logger.info("marketplace.delete", marketplace_id=marketplace_id, user_id=user_id)
        return True

    def sync(self, marketplace_id: str, user_id: str) -> MarketplaceRegistry | None:
        """Re-fetch the catalog for a marketplace owned by the user."""
        entry = (
            self._db.query(MarketplaceRegistry)
            .filter(
                MarketplaceRegistry.id == marketplace_id,
                MarketplaceRegistry.created_by == user_id,
            )
            .first()
        )
        if entry is None:
            return None
        catalog, fetched_at = self._try_fetch(entry.url)
        if catalog is not None:
            entry.catalog_json = catalog
            entry.last_fetched_at = fetched_at
            self._db.commit()
            self._db.refresh(entry)
            logger.info("marketplace.sync.ok", marketplace_id=marketplace_id)
        else:
            logger.warning("marketplace.sync.fetch_failed", marketplace_id=marketplace_id)
        return entry

    def get_by_id(self, marketplace_id: str, user_id: str) -> MarketplaceRegistry | None:
        return (
            self._db.query(MarketplaceRegistry)
            .filter(
                MarketplaceRegistry.id == marketplace_id,
                MarketplaceRegistry.created_by == user_id,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # Internal — HTTP fetch
    # ------------------------------------------------------------------

    @staticmethod
    def _try_fetch(url: str) -> tuple[dict[str, Any] | None, datetime | None]:
        """Fetch + parse the marketplace.json. Returns (catalog_dict, timestamp)
        on success, (None, None) on any failure (DNS, non-2xx, oversize, JSON
        decode, shape mismatch).
        """
        try:
            with httpx.Client(timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                logger.warning("marketplace.fetch.http_error", url=url, status=resp.status_code)
                return None, None
            if len(resp.content) > _FETCH_MAX_BYTES:
                logger.warning("marketplace.fetch.oversize", url=url, size=len(resp.content))
                return None, None
            parsed = resp.json()
            if not isinstance(parsed, dict) or not isinstance(parsed.get("plugins"), list):
                logger.warning("marketplace.fetch.shape_invalid", url=url)
                return None, None
            return parsed, datetime.now(timezone.utc)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("marketplace.fetch.exception", url=url, error=str(exc))
            return None, None
