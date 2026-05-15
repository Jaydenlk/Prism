"""
Prism v2 — Admin Stats Service (DOC-09 Task 9.3)

ADR-085: GET /admin/stats/dashboard returns SystemStatsResponse with:
  - runs_24h / runs_7d / cost_usd_7d / cache_savings_usd_7d
  - harness_events_24h: dict[action, count] for harness.* events
  - active_sessions / active_users_24h
  - component_health: {postgres, redis, providers}

Cache savings estimate: cache_hit_tokens * $0.30 / 1 000 000 * 90%
(matches the $0.27/1M read savings used in UsageService._compute_cache_savings)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.run import Run
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.admin import SystemStatsResponse

import structlog
logger = structlog.get_logger()

# Cache savings rate: $0.30 per 1M tokens * 90% discount
_CACHE_SAVINGS_PER_TOKEN = 0.30 / 1_000_000 * 0.90


class AdminStatsService:
    """Aggregate system-wide statistics for the admin dashboard.

    Parameters
    ----------
    db:
        Synchronous SQLAlchemy session (used for all DB queries).
    redis_client:
        Async Redis client (redis.asyncio.Redis) — used only for ping and
        scanning harness:circuit:* keys to detect broken Providers.
    settings:
        App settings instance (currently unused but kept for future use).
    """

    def __init__(self, db: Session, redis_client: Any, settings: Any) -> None:
        self._db = db
        self._redis = redis_client
        self._settings = settings

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def get_dashboard(self) -> SystemStatsResponse:
        """Compute and return a SystemStatsResponse snapshot."""
        now = datetime.now(timezone.utc)
        t24h = now - timedelta(hours=24)
        t7d = now - timedelta(days=7)

        # --- Runs --------------------------------------------------------
        runs_24h: int = (
            self._db.query(Run).filter(Run.created_at >= t24h).count()
        )

        runs_7d_rows = (
            self._db.query(Run).filter(Run.created_at >= t7d).all()
        )
        runs_7d = len(runs_7d_rows)

        cost_usd_7d: float = round(
            sum((r.cost_usd or 0.0) for r in runs_7d_rows), 4
        )
        cache_savings_usd_7d: float = round(
            sum((r.cache_hit_tokens or 0) * _CACHE_SAVINGS_PER_TOKEN
                for r in runs_7d_rows),
            4,
        )

        # --- Harness events (24 h) ----------------------------------------
        harness_rows = (
            self._db.query(AuditLog.action, func.count())
            .filter(AuditLog.created_at >= t24h)
            .filter(AuditLog.action.like("harness.%"))
            .group_by(AuditLog.action)
            .all()
        )
        harness_events_24h: dict[str, int] = {
            action: cnt for action, cnt in harness_rows
        }

        # --- Active sessions & users ----------------------------------------
        active_sessions: int = (
            self._db.query(SessionModel)
            .filter(SessionModel.status == "running")
            .count()
        )
        active_users_24h: int = (
            self._db.query(User)
            .filter(User.last_login_at >= t24h)
            .count()
        )

        # --- Component health (Redis + Provider circuit breakers) -----------
        health: dict[str, str] = {
            "postgres": "healthy",
            "redis": "healthy",
        }
        try:
            await self._redis.ping()
        except Exception as exc:
            logger.warning("admin_stats: Redis ping failed: %s", exc)
            health["redis"] = "unhealthy"

        # Count broken Providers by scanning harness:circuit:* keys
        broken_count = 0
        try:
            async for _ in self._redis.scan_iter(match="harness:circuit:*"):
                broken_count += 1
        except Exception as exc:
            logger.warning("admin_stats: Redis scan_iter failed: %s", exc)
        health["providers"] = f"{broken_count} broken" if broken_count else "healthy"

        return SystemStatsResponse(
            runs_24h=runs_24h,
            runs_7d=runs_7d,
            cost_usd_7d=cost_usd_7d,
            cache_savings_usd_7d=cache_savings_usd_7d,
            harness_events_24h=harness_events_24h,
            active_sessions=active_sessions,
            active_users_24h=active_users_24h,
            component_health=health,
            timestamp=now,
        )
