"""
MarketplaceService — Skills Marketplace registry (DOC-SK R1, ADR-086 → Session 4c ADR-090)

Stores user-registered Claude Code-format marketplaces (`marketplace_registry`
table) and caches their `.claude-plugin/marketplace.json` catalog.

Session 4c adds dual-mode fetch:
  - URL-based: URL ends with .json → direct httpx GET (Session 3 Phase 1 behavior)
  - Git-based: owner/repo shorthand OR .git / https URL → git clone + read
    .claude-plugin/marketplace.json (enables relative-path plugin source resolution)

install_plugin() dispatches 5-source resolver (source_resolver.py) to download
plugin package, parses skills/<name>/SKILL.md, UPSERTs skill_installs rows.

Fetching is best-effort on create/sync: registration with unreachable URL still
succeeds (catalog_json null); call `sync()` to retry.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import structlog
import yaml
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.marketplace import MarketplaceRegistry
from app.schemas.marketplace import InstallReport
from app.services.skill_install_service import SkillInstallService
from app.services.source_resolver import (
    SourceDownloadError,
    resolve_and_download,
)

logger = structlog.get_logger()

_FETCH_TIMEOUT_SECONDS = 10.0
_FETCH_MAX_BYTES = 1024 * 1024  # 1 MiB — catalogs are JSON text, not binaries

# Session 4c — cache dirs for git-based marketplaces + plugin downloads
_DATA_DIR = Path(os.getenv("PRISM_DATA_DIR", "/app/data"))
_MARKETPLACE_CACHE = _DATA_DIR / "marketplace_cache"
_PLUGIN_CACHE = _DATA_DIR / "plugin_cache"

_JSON_URL_RE = re.compile(r"\.json(?:\?.*)?$", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Module helpers (Session 4c)
# -----------------------------------------------------------------------------


def _is_safe_marketplace_url(url: str) -> bool:
    """Scheme allowlist: accept HTTPS, owner/repo shorthand. Reject http://
    (MITM), file://, ftp://, AWS metadata IPs, etc. (SSRF defense).
    """
    if not url:
        return False
    if url.startswith("https://"):
        return True
    if url.startswith("git@"):
        return False  # SSH not supported (no HTTPS fallback in Prism)
    if url.startswith(("http://", "file://", "ftp://")):
        return False
    # owner/repo shorthand: must contain exactly one '/' and no scheme
    if "://" not in url and url.count("/") >= 1:
        return True
    return False


def _looks_like_json_url(url: str) -> bool:
    """Detect URL-based marketplace (direct JSON GET) vs git-based (clone)."""
    if not url.startswith(("http://", "https://")):
        return False  # owner/repo shorthand is git-based
    if url.endswith(".git"):
        return False
    return bool(_JSON_URL_RE.search(url))


def _safe_name_from_url(url: str) -> str:
    """URL → filesystem-safe marketplace cache dir name."""
    cleaned = re.sub(r"^https?://|^git@|\.git$", "", url)
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", cleaned).strip("_")
    return (cleaned[:80]) or "mp"


def _validate_marketplace_shape(parsed: Any) -> bool:
    """Validate .claude-plugin/marketplace.json per CC official docs.

    Required: name (str), owner.name (str), plugins (list).
    Permissive on source: string or object (per anthropic issue #1331 — official
    marketplace.json mixes both forms).
    """
    if not isinstance(parsed, dict):
        return False
    if not isinstance(parsed.get("name"), str):
        return False
    owner = parsed.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str):
        return False
    plugins = parsed.get("plugins")
    if not isinstance(plugins, list):
        return False
    for p in plugins:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str):
            return False
        src = p.get("source")
        if not (isinstance(src, str) or isinstance(src, dict)):
            return False
    return True


def _fetch_json(
    url: str,
) -> tuple[dict[str, Any] | None, datetime | None]:
    """URL-based fetch — direct httpx GET (Session 3 Phase 1 behavior)."""
    try:
        with httpx.Client(
            timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            logger.warning(
                "marketplace.fetch.http_error", url=url, status=resp.status_code
            )
            return None, None
        if len(resp.content) > _FETCH_MAX_BYTES:
            logger.warning(
                "marketplace.fetch.oversize", url=url, size=len(resp.content)
            )
            return None, None
        parsed = resp.json()
        if not _validate_marketplace_shape(parsed):
            logger.warning("marketplace.fetch.shape_invalid", url=url)
            return None, None
        return parsed, datetime.now(timezone.utc)
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("marketplace.fetch.exception", url=url, error=str(exc))
        return None, None


def _fetch_git(
    url: str,
) -> tuple[dict[str, Any] | None, datetime | None, Path | None]:
    """Git-based fetch — clone + read .claude-plugin/marketplace.json.

    Returns (catalog, fetched_at, local_clone_dir).
    local_clone_dir is preserved for relative-path plugin installs later.
    """
    original_url = url
    if "/" in url and not url.startswith(("http", "git@")):
        url = f"https://github.com/{url}.git"
    if url.startswith("git@"):
        logger.warning("marketplace.fetch.ssh_unsupported", url=original_url)
        return None, None, None

    cache_dir = _MARKETPLACE_CACHE / _safe_name_from_url(url)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    from app.services.source_resolver import _inject_github_token

    token = os.getenv("GITHUB_TOKEN")
    clone_url = _inject_github_token(url, token)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(cache_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "marketplace.fetch.clone_error", url=original_url, error=str(exc)
        )
        return None, None, None
    if result.returncode != 0:
        logger.warning(
            "marketplace.fetch.clone_failed",
            url=original_url,
            stderr=result.stderr[:200],
        )
        return None, None, None

    mj = cache_dir / ".claude-plugin" / "marketplace.json"
    if not mj.exists():
        logger.warning(
            "marketplace.fetch.no_marketplace_json", url=original_url
        )
        return None, None, cache_dir
    try:
        parsed = json.loads(mj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning(
            "marketplace.fetch.json_decode_error", url=original_url
        )
        return None, None, cache_dir
    if not _validate_marketplace_shape(parsed):
        logger.warning("marketplace.fetch.shape_invalid", url=original_url)
        return None, None, cache_dir
    return parsed, datetime.now(timezone.utc), cache_dir


def _safe_path_segment(name: str) -> str:
    """Sanitize a user-supplied string for use as a filesystem path segment.

    Prevents path injection (e.g. mp.name="../../evil") — reject anything
    outside [A-Za-z0-9._-].
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:100]
    return cleaned or "unnamed"


@asynccontextmanager
async def _redis_install_lock(key: str, ttl: int = 120) -> "AsyncIterator[None]":
    """SETNX EX lock (concurrent install guard). Uses redis.asyncio."""
    import redis.asyncio as aioredis

    from app.core.config import get_settings

    settings = get_settings()
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        got = await r.set(key, "1", nx=True, ex=ttl)
        if not got:
            raise HTTPException(
                status_code=409,
                detail="Install already in progress for this plugin",
            )
        try:
            yield
        finally:
            try:
                await r.delete(key)
            except Exception as exc:
                logger.warning(
                    "marketplace.lock.release_error", key=key, error=str(exc)
                )
    finally:
        await r.aclose()


def _parse_skill_frontmatter(skill_md_path: Path) -> tuple[str, str, str]:
    """Parse SKILL.md YAML frontmatter → (skill_name, description, version).

    Raises ValueError on missing / malformed frontmatter.
    """
    text = skill_md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError(f"{skill_md_path} missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{skill_md_path} malformed frontmatter")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{skill_md_path} frontmatter not a mapping")
    skill_name = meta.get("name") or skill_md_path.parent.name
    description = meta.get("description", "") or ""
    version = meta.get("version", "0.0.0") or "0.0.0"
    return str(skill_name), str(description), str(version)


# -----------------------------------------------------------------------------
# Service class
# -----------------------------------------------------------------------------


class MarketplaceService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public CRUD (Session 3 Phase 1 — unchanged interface)
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
        return (
            self._db.query(MarketplaceRegistry)
            .filter(MarketplaceRegistry.created_by == user_id)
            .order_by(MarketplaceRegistry.created_at.desc())
            .all()
        )

    def delete(self, marketplace_id: str, user_id: str) -> bool:
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
        logger.info(
            "marketplace.delete", marketplace_id=marketplace_id, user_id=user_id
        )
        return True

    def sync(
        self, marketplace_id: str, user_id: str
    ) -> MarketplaceRegistry | None:
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
            logger.warning(
                "marketplace.sync.fetch_failed",
                marketplace_id=marketplace_id,
            )
        return entry

    def get_by_id(
        self, marketplace_id: str, user_id: str
    ) -> MarketplaceRegistry | None:
        return (
            self._db.query(MarketplaceRegistry)
            .filter(
                MarketplaceRegistry.id == marketplace_id,
                MarketplaceRegistry.created_by == user_id,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # Session 4c additions
    # ------------------------------------------------------------------

    @staticmethod
    def _try_fetch(url: str) -> tuple[dict[str, Any] | None, datetime | None]:
        """Session 4c: dual-mode dispatch with SSRF scheme allowlist.

        URL-based (ends with .json) → _fetch_json (Session 3 Phase 1 behavior).
        Git-based (owner/repo / .git / https non-json) → _fetch_git + clone.
        Non-HTTPS / file:// / ftp:// / http:// rejected (ADR-090 hardening).
        """
        if not _is_safe_marketplace_url(url):
            logger.warning("marketplace.fetch.unsafe_url_rejected", url=url)
            return None, None
        if _looks_like_json_url(url):
            return _fetch_json(url)
        catalog, ts, _local = _fetch_git(url)
        return catalog, ts

    def _get_marketplace_local_dir(
        self, mp: MarketplaceRegistry
    ) -> Path | None:
        """Return local clone path if git-based marketplace; None for URL-based."""
        if _looks_like_json_url(mp.url):
            return None
        url_normalized = mp.url
        if "/" in url_normalized and not url_normalized.startswith(("http", "git@")):
            url_normalized = f"https://github.com/{url_normalized}.git"
        return _MARKETPLACE_CACHE / _safe_name_from_url(url_normalized)

    def bootstrap_default_marketplace(self, created_by: str) -> None:
        """Register default Anthropic plugin marketplace if registry is empty.

        Idempotent: skips if any marketplace already exists (DEC-004).
        created_by must be a valid user id (caller passes admin id from lifespan).
        """
        exists = (
            self._db.query(MarketplaceRegistry)
            .filter(MarketplaceRegistry.name == "anthropics/claude-plugins-official")
            .first()
        )
        if exists is not None:
            logger.info("marketplace.bootstrap_skipped", reason="default_already_registered")
            return
        default = MarketplaceRegistry(
            name="anthropics/claude-plugins-official",
            url="https://github.com/anthropics/claude-plugins-official",
            catalog_json={"plugins": []},
            created_by=created_by,
        )
        self._db.add(default)
        self._db.commit()
        self._db.refresh(default)
        logger.info("marketplace.bootstrap_default", name=default.name)
        # Pull real catalog from GitHub so Skills Market search has data immediately.
        # First cold boot blocks ~5-15s on the network fetch; subsequent boots
        # take the early-return path above.
        try:
            self.sync(marketplace_id=default.id, user_id=created_by)
        except Exception as exc:
            logger.warning(
                "marketplace.bootstrap_sync_failed",
                marketplace_id=default.id,
                error=str(exc),
            )

    async def install_plugin(
        self, marketplace_id: str, plugin_name: str, user_id: str
    ) -> InstallReport:
        """Install one plugin from a marketplace catalog (Session 4c).

        Flow:
          1. Lookup marketplace + plugin entry (404 if missing)
          2. Acquire Redis SETNX lock (409 if another install in progress)
          3. Dispatch 5-source resolver → download to plugin_cache
          4. Enumerate skills/<name>/SKILL.md entries (422 if none)
          5. For each SKILL.md: parse frontmatter + call
             SkillInstallService.install() (UPSERT skill_installs row with
             source='marketplace', marketplace_id FK)
          6. Return InstallReport (plugin + installed_skills[] + failures[])
        """
        mp = self.get_by_id(marketplace_id, user_id)
        if mp is None:
            raise HTTPException(404, "Marketplace not found")
        catalog = mp.catalog_json or {}
        plugins = catalog.get("plugins", [])
        entry = next((p for p in plugins if p.get("name") == plugin_name), None)
        if entry is None:
            raise HTTPException(
                404, f"Plugin {plugin_name!r} not in catalog"
            )

        lock_key = f"install_lock:{marketplace_id}:{plugin_name}"
        async with _redis_install_lock(lock_key, ttl=120):
            version = entry.get("version", "0.0.0")
            # Sanitize path segments — mp.name / plugin_name / version are
            # all user-controlled (catalog_json); block path traversal.
            target_dir = (
                _PLUGIN_CACHE
                / _safe_path_segment(mp.name)
                / _safe_path_segment(plugin_name)
                / _safe_path_segment(version)
            )
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)

            marketplace_local = self._get_marketplace_local_dir(mp)
            github_token = os.getenv("GITHUB_TOKEN")
            try:
                await resolve_and_download(
                    entry["source"],
                    target_dir,
                    marketplace_local,
                    github_token,
                )
            except SourceDownloadError as exc:
                logger.warning(
                    "marketplace.install.download_failed",
                    marketplace_id=marketplace_id,
                    plugin=plugin_name,
                    stage=exc.stage,
                )
                raise HTTPException(
                    422, f"Download failed [{exc.stage}]: {exc.hint}"
                )

            skills_dir = target_dir / "skills"
            if not skills_dir.is_dir():
                raise HTTPException(
                    422,
                    f"Plugin {plugin_name!r} has no skills/ directory. "
                    "Prism currently only supports skill-type plugins "
                    "(agents/hooks/mcpServers follow-up).",
                )

            install_svc = SkillInstallService(self._db)
            installed: list[str] = []
            failures: list[dict[str, str]] = []
            for skill_subdir in sorted(skills_dir.iterdir()):
                if not skill_subdir.is_dir():
                    continue
                skill_md = skill_subdir / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    skill_name, _desc, skill_version = _parse_skill_frontmatter(
                        skill_md
                    )
                    install_svc.install(
                        user_id=user_id,
                        skill_name=skill_name,
                        source="marketplace",
                        source_url=mp.url,
                        version=skill_version or version,
                        install_path=str(skill_subdir),
                        has_hooks=(target_dir / "hooks").exists()
                        or (target_dir / "hooks.json").exists(),
                        has_mcp=(target_dir / ".mcp.json").exists(),
                        marketplace_id=mp.id,
                    )
                    installed.append(skill_name)
                except Exception as exc:
                    failures.append(
                        {"skill_dir": skill_subdir.name, "error": str(exc)[:200]}
                    )
                    logger.warning(
                        "marketplace.install.skill_failed",
                        marketplace_id=marketplace_id,
                        plugin=plugin_name,
                        skill=skill_subdir.name,
                        error=str(exc),
                    )

            if not installed and failures:
                raise HTTPException(
                    422,
                    f"All skills failed to install for {plugin_name!r}: "
                    + "; ".join(f["error"] for f in failures),
                )

            logger.info(
                "marketplace.install.ok",
                marketplace_id=marketplace_id,
                plugin=plugin_name,
                installed_count=len(installed),
                failure_count=len(failures),
            )
            return InstallReport(
                plugin_name=plugin_name,
                installed_skills=installed,
                failures=failures,
            )
