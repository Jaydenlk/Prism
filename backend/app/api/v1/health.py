"""
Prism v2 — Health Check Endpoints (ADR-114, DOC-12 Task 12.3)

Three sub-endpoints per K8s/Docker probe conventions:

  GET /health/live     — liveness probe: 200 as long as process is alive,
                         no dependency checks, fastest response
  GET /health/ready    — readiness probe: checks DB + Redis; returns 503
                         if any critical dependency is unreachable
  GET /health/detailed — admin-only: full report (resource metrics,
                         subprocess count, provider circuit-breaker states)

ADR-114: /health split into live/ready/detailed
ADR-111: ResourceMonitor percentage thresholds (70% warn / 85% critical)
"""
from __future__ import annotations

import time
from typing import Any

import redis as redis_sync
import sqlalchemy
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.dependencies import require_admin
from app.models.user import User

router = APIRouter(tags=["health"])

# Module-level start time for uptime calculation
_START_TIME: float = time.time()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_database() -> str:
    """Synchronously verify the DB responds to SELECT 1.

    Returns "ok" on success or an error string on failure.
    """
    try:
        engine = sqlalchemy.create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


def _check_redis() -> str:
    """Synchronously verify Redis responds to PING.

    Returns "ok" on success or an error string on failure.
    """
    try:
        r = redis_sync.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        r.ping()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


# ---------------------------------------------------------------------------
# ADR-114: /health/live — liveness probe
# ---------------------------------------------------------------------------

@router.get("/health/live", summary="Liveness probe")
async def health_live() -> dict[str, str]:
    """Liveness probe — returns 200 as long as the process is alive.

    ADR-114: Does NOT check any external dependency.  K8s/Docker will
    restart the container only when this endpoint fails (process dead).
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# ADR-114: /health/ready — readiness probe
# ---------------------------------------------------------------------------

@router.get("/health/ready", summary="Readiness probe")
async def health_ready() -> JSONResponse:
    """Readiness probe — checks DB + Redis connectivity.

    Returns 200 ``{"status":"ok","checks":{...}}`` when all critical
    dependencies are reachable, or 503 with per-check failure details.

    ADR-114: Load balancers remove the container from rotation on 503.
    """
    checks: dict[str, str] = {}
    overall_ok = True

    db_status = _check_database()
    checks["database"] = db_status
    if db_status != "ok":
        overall_ok = False

    redis_status = _check_redis()
    checks["redis"] = redis_status
    if redis_status != "ok":
        overall_ok = False

    status_code = 200 if overall_ok else 503
    body: dict[str, Any] = {
        "status": "ok" if overall_ok else "unhealthy",
        "checks": checks,
    }
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# ADR-114: /health/detailed — admin-only full report
# ---------------------------------------------------------------------------

@router.get("/health/detailed", summary="Detailed health report (admin only)")
async def health_detailed(
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only detailed health report.

    Returns DB/Redis status, resource metrics (ADR-111: memory/CPU
    percentage thresholds), subprocess count, provider circuit-breaker
    states, and backend uptime.
    """
    # --- dependency checks (same logic as /ready) --------------------------
    db_status = _check_database()
    redis_status = _check_redis()
    deps_ok = db_status == "ok" and redis_status == "ok"

    # --- resource metrics (ADR-111) ----------------------------------------
    resource_info: dict[str, Any] = {}
    try:
        from app.services.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        resource_info = monitor.check_health()
    except Exception as exc:  # noqa: BLE001
        resource_info = {"error": str(exc)}

    # --- subprocess count ---------------------------------------------------
    agent_info: dict[str, Any] = {}
    try:
        import psutil
        import os

        parent = psutil.Process(os.getpid())
        child_count = len(parent.children(recursive=True))
        agent_info = {
            "running": child_count,
            "max": settings.MAX_CONCURRENT_RUNS,
        }
    except Exception as exc:  # noqa: BLE001
        agent_info = {"error": str(exc)}

    # --- provider circuit-breaker states ------------------------------------
    provider_info: dict[str, Any] = {}
    try:
        import redis as redis_sync_prov

        r = redis_sync_prov.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        circuit_keys = list(r.scan_iter("harness:circuit:*"))
        broken = [k.decode() if isinstance(k, bytes) else k for k in circuit_keys]
        provider_info = {
            "circuit_breakers_open": len(broken),
            "open_keys": broken[:20],  # cap at 20 to keep response small
        }
    except Exception as exc:  # noqa: BLE001
        provider_info = {"error": str(exc)}

    # --- uptime -------------------------------------------------------------
    uptime_seconds = int(time.time() - _START_TIME)

    overall_status = "ok" if deps_ok else "degraded"
    resource_status = resource_info.get("status", "unknown")
    if resource_status == "critical":
        overall_status = "critical"
    elif resource_status == "warning" and overall_status == "ok":
        overall_status = "warning"

    return {
        "status": overall_status,
        "checks": {
            "database": db_status,
            "redis": redis_status,
        },
        "resources": resource_info,
        "agents": agent_info,
        "providers": provider_info,
        "version": "2.0.0",
        "uptime_seconds": uptime_seconds,
    }
