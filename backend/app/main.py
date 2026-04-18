"""
Prism v2 — FastAPI application entry point (DOC-02 Task 2.1 Step 5)

Startup sequence (lifespan):
  1. validate_secrets()        — ADR-004/ADR-050: three keys must be distinct >= 32 chars
  2. init_logging()            — ADR-118: structlog JSON + contextvars
  3. Import metrics registry   — ADR-116: registers all Prometheus metrics
  4. Log "Prism v2 is ready"

Health endpoints (ADR-115, DOC-12 Task 12.3):
  GET /health/live     — liveness probe (always 200 if process is alive)
  GET /health/ready    — readiness probe (checks DB + Redis)
  GET /health/detailed — admin-only detailed report (placeholder)

Metrics endpoint (ADR-116, DOC-12 Task 12.4):
  GET /metrics         — admin-only Prometheus text format
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.security import validate_secrets
from app.observability.logging import init_logging
from app.observability.metrics import REGISTRY  # triggers metric registration

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context manager — runs startup then yields."""

    # 1. Three-secret validation (ADR-004 / ADR-050) — must be first
    validate_secrets(
        jwt_secret=settings.JWT_SECRET,
        encryption_key=settings.ENCRYPTION_KEY,
        callback_secret=settings.CALLBACK_SECRET,
    )

    # 2. Structured logging (ADR-118)
    init_logging(level="DEBUG" if settings.PRISM_ENV == "development" else "INFO")

    # 3. Prometheus registry is already populated by the import above
    logger.info(
        "prism.startup",
        env=settings.PRISM_ENV,
        metrics_enabled=settings.PROMETHEUS_METRICS_ENABLED,
    )

    # 4. Bootstrap built-in provider presets (ADR-010: scope='system', idempotent)
    try:
        from app.core.database import SessionLocal
        from app.services.provider_service import ProviderService

        with SessionLocal() as db:
            inserted = ProviderService.bootstrap_presets(db)
            logger.info(
                "prism.provider_bootstrap",
                inserted=inserted,
                message=f"Provider presets bootstrapped ({inserted} new).",
            )
    except Exception as exc:
        # Bootstrap 失败不阻止启动(DB 可能未就绪);运行时懒加载
        logger.warning(
            "prism.provider_bootstrap_failed",
            error=str(exc),
            message="Provider preset bootstrap failed (DB may not be ready). Will retry on first request.",
        )

    logger.info("prism.ready", message="Prism v2 is ready to serve requests.")

    yield  # application serves requests here

    logger.info("prism.shutdown", message="Prism v2 shutting down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Prism v2",
    description="Self-hosted AI Agent Operating System with Harness Runtime",
    version="0.1.0",
    lifespan=lifespan,
)

# Register v1 API router
app.include_router(api_v1_router)

# CORS — development only; tighten in production via PRISM_ENV guard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.PRISM_ENV == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handler — uniform ErrorResponse envelope
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:  # noqa: ANN401
    logger.error("prism.unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


# ---------------------------------------------------------------------------
# Health endpoints (ADR-115 / DOC-12 Task 12.3)
# ---------------------------------------------------------------------------

@app.get("/health/live", tags=["health"], response_model=dict)
async def health_live() -> dict[str, str]:
    """Liveness probe — returns 200 as long as the process is alive."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"], response_model=dict)
async def health_ready() -> JSONResponse:
    """Readiness probe — checks DB and Redis connectivity.

    Returns 200 with ``{"checks": {"database": "ok", "redis": "ok"}}`` when
    all dependencies are reachable, or 503 with per-check details otherwise.
    """
    checks: dict[str, str] = {}
    overall_ok = True

    # --- Database check ---
    try:
        import sqlalchemy
        from sqlalchemy import text

        from app.core.config import settings as s
        engine = sqlalchemy.create_engine(s.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        overall_ok = False

    # --- Redis check ---
    try:
        import redis as redis_lib

        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JSONResponse(status_code=status_code, content={"checks": checks})


@app.get("/health/detailed", tags=["health"])
async def health_detailed() -> dict[str, Any]:
    """Detailed health report — admin only (full implementation in DOC-12 Task 12.3).

    Returns an empty object as placeholder until the admin dependency and
    resource monitor are implemented in Task 12.3.
    """
    # TODO-DOC12: add Depends(require_admin) and populate resource stats
    return {}


# ---------------------------------------------------------------------------
# Metrics endpoint (ADR-116 / DOC-12 Task 12.4)
# ---------------------------------------------------------------------------

@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    """Expose Prometheus metrics in text format.

    Full admin-auth guard added in DOC-12 Task 12.4 once the auth dependency
    chain is wired.  During skeleton phase the endpoint is open so that
    ``docker compose`` health-checks and CI can scrape without credentials.
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
