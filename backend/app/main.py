"""
Prism v2 — FastAPI application entry point (DOC-02 Task 2.1 Step 5)

Startup sequence (lifespan):
  1. validate_secrets()        — ADR-004/ADR-050: three keys must be distinct >= 32 chars
  2. init_logging()            — ADR-118: structlog JSON + contextvars
  3. Import metrics registry   — ADR-116: registers all Prometheus metrics
  4. Bootstrap provider presets + admin user
  5. Initialize ProcessManager — ADR-066: subprocess scheduler (MAX_CONCURRENT_RUNS)
  6. Log "Prism v2 is ready"
  7. Start HeartbeatMonitor    — ADR-065: 每 10s 扫 harness:heartbeat:*，超 30s 标记 crashed

Health endpoints (ADR-114/ADR-115, DOC-12 Task 12.3):
  GET /api/v1/health/live     — liveness probe (always 200, no dep check)
  GET /api/v1/health/ready    — readiness probe (checks DB + Redis, 503 on failure)
  GET /api/v1/health/detailed — admin-only full report (resources + providers)
  GET /health/live            — top-level alias for Docker/K8s probes
  GET /health/ready           — top-level alias for Docker/K8s probes

Metrics endpoint (ADR-116, DOC-12 Task 12.4):
  GET /metrics         — admin-only Prometheus text format
"""
from __future__ import annotations

import asyncio
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
from app.observability.logging import StructlogRequestMiddleware, init_logging
from app.observability.metrics import REGISTRY  # triggers metric registration
from app.observability.tracing import init_tracing

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
    _dev = settings.PRISM_ENV == "development"
    init_logging(level="DEBUG" if _dev else "INFO", dev_mode=_dev)

    # 2b. OTel Tracing (ADR-117, DOC-12 Task 12.5)
    init_tracing(settings)
    logger.info(
        "prism.tracing_initialized",
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT or "stdout(dev)",
        service_name=settings.OTEL_SERVICE_NAME,
    )

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

    # 4b. Bootstrap built-in MCP Servers (DOC-09 Task 9.1: scope='system', idempotent)
    try:
        from app.core.database import SessionLocal
        from app.services.mcp_service import MCPService

        with SessionLocal() as db:
            MCPService(db).register_builtin_servers()
            logger.info("prism.mcp_bootstrap", message="MCP built-in servers bootstrapped.")
    except Exception as exc:
        logger.warning(
            "prism.mcp_bootstrap_failed",
            error=str(exc),
            message="MCP built-in server bootstrap failed (DB may not be ready). Will retry on next startup.",
        )

    # 5. Ensure admin user exists (DOC-06 Task 6.1 — idempotent, ADR-050)
    try:
        from app.core.database import SessionLocal
        from app.services.auth_service import AuthService

        with SessionLocal() as db:
            AuthService(db, settings).ensure_admin()
            db.commit()
            logger.info(
                "prism.admin_bootstrap",
                message="Admin user bootstrapped (idempotent).",
            )
    except Exception as exc:
        logger.warning(
            "prism.admin_bootstrap_failed",
            error=str(exc),
            message="Admin bootstrap failed (DB may not be ready). Will retry on next startup.",
        )

    # 5b. Bootstrap default marketplace (idempotent, requires admin to exist)
    try:
        from app.core.database import SessionLocal
        from app.models.user import User
        from app.services.marketplace_service import MarketplaceService

        with SessionLocal() as db:
            admin = db.query(User).filter(User.role == "admin").first()
            if admin is not None:
                MarketplaceService(db).bootstrap_default_marketplace(admin.id)
            else:
                logger.info("prism.marketplace_bootstrap_skipped", reason="no_admin_user")
    except Exception as exc:
        logger.warning(
            "prism.marketplace_bootstrap_failed",
            error=str(exc),
            message="Marketplace bootstrap failed (DB may not be ready).",
        )

    # 6. Initialize ProcessManager singleton (ADR-066 subprocess scheduler)
    try:
        from app.services.process_manager import ProcessManager

        process_manager = ProcessManager(settings)
        app.state.process_manager = process_manager
        logger.info(
            "prism.process_manager_started",
            max_concurrent=settings.MAX_CONCURRENT_RUNS,
            timeout=settings.RUN_TIMEOUT_SECONDS,
            message="ProcessManager initialized (ADR-066).",
        )
    except Exception as exc:
        app.state.process_manager = None
        logger.warning(
            "prism.process_manager_failed",
            error=str(exc),
            message="ProcessManager failed to initialize. Subprocess scheduling disabled.",
        )

    # 6b. Initialize IMGateway + adapters (Feishu / Slack / Discord — DOC-IM2 ADR-088)
    try:
        import redis.asyncio as _aioredis
        from app.services.im_gateway import IMGateway
        from app.services.im_feishu import FeishuAdapter
        from app.services.im_slack import SlackAdapter
        from app.services.im_discord import DiscordAdapter

        # Single DB round-trip for all IM channel configs + batch decrypt.
        def _load_all_im_configs(channels: tuple[str, ...]) -> dict[str, dict]:
            try:
                from app.core.database import SessionLocal
                from app.models.im import ImChannelConfig
                from app.services.credential_cipher import decrypt_config_secrets

                _s = SessionLocal()
                try:
                    rows = (
                        _s.query(ImChannelConfig)
                        .filter(ImChannelConfig.channel.in_(channels))
                        .all()
                    )
                    raw = {r.channel: dict(r.config or {}) for r in rows}
                finally:
                    _s.close()
                key_hex = settings.ENCRYPTION_KEY
                return {
                    ch: decrypt_config_secrets(raw.get(ch, {}), key_hex)
                    for ch in channels
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("im.configs_load_failed", error=str(exc))
                return {ch: {} for ch in channels}

        im_configs = _load_all_im_configs(("feishu", "slack", "discord"))
        _redis_for_im = _aioredis.from_url(settings.REDIS_URL, decode_responses=False)
        feishu_adapter = FeishuAdapter(
            config=im_configs["feishu"],
            settings=settings,
            redis_client=_redis_for_im,
        )
        slack_adapter = SlackAdapter(config=im_configs["slack"], settings=settings)
        discord_adapter = DiscordAdapter(config=im_configs["discord"], settings=settings)

        im_gateway = IMGateway(settings)
        im_gateway.register_adapter(feishu_adapter)
        im_gateway.register_adapter(slack_adapter)
        im_gateway.register_adapter(discord_adapter)
        app.state.im_gateway = im_gateway
        await im_gateway.start_all()
        logger.info(
            "prism.im_gateway_started",
            message="IMGateway initialized with Feishu + Slack + Discord adapters (DOC-IM2).",
            feishu_configured=feishu_adapter.is_configured(),
            slack_configured=slack_adapter.is_configured(),
            discord_configured=discord_adapter.is_configured(),
        )
    except Exception as exc:
        app.state.im_gateway = None
        logger.warning(
            "prism.im_gateway_failed",
            error=str(exc),
            message="IMGateway failed to initialize. Feishu bot disabled.",
        )

    logger.info("prism.ready", message="Prism v2 is ready to serve requests.")

    # 7. Start HeartbeatMonitor background task (ADR-065)
    heartbeat_task: asyncio.Task | None = None
    heartbeat_monitor = None
    try:
        import redis.asyncio as aioredis
        from app.core.database import SessionLocal
        from app.services.heartbeat_monitor import HeartbeatMonitor
        from app.services.run_lifecycle import RunLifecycle

        _redis_for_hb = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
        _db_for_hb = SessionLocal()
        _lifecycle_for_hb = RunLifecycle(_db_for_hb)

        heartbeat_monitor = HeartbeatMonitor(
            redis_client=_redis_for_hb,
            lifecycle=_lifecycle_for_hb,
            scan_interval=10,
            stale_threshold=30,
        )
        heartbeat_task = asyncio.create_task(heartbeat_monitor.run())
        logger.info("prism.heartbeat_monitor_started", message="HeartbeatMonitor started (ADR-065).")
    except Exception as exc:
        logger.warning(
            "prism.heartbeat_monitor_failed",
            error=str(exc),
            message="HeartbeatMonitor failed to start. Zombie Run detection disabled.",
        )

    # 8. Start Entropy Detector background scheduler (ADR-112: hourly global scan)
    async def _entropy_scheduler() -> None:
        from app.core.database import SessionLocal
        from app.services.entropy_detector import EntropyDetector
        from app.services.harness_analytics import HarnessAnalytics

        def _run_detection() -> list:
            db = SessionLocal()
            try:
                analytics = HarnessAnalytics(db)
                detector = EntropyDetector(db, analytics)
                return detector.detect(user_id=None)
            finally:
                db.close()

        while True:
            await asyncio.sleep(3600)
            try:
                alerts = await asyncio.to_thread(_run_detection)
                if alerts:
                    logger.warning("entropy.alerts_detected", count=len(alerts))
            except Exception as exc:
                logger.warning("entropy.scheduler_error", error=str(exc))

    entropy_task: asyncio.Task | None = None
    entropy_task = asyncio.create_task(_entropy_scheduler())
    logger.info("prism.entropy_scheduler_started", message="Entropy scheduler started (ADR-112, 3600s interval).")

    yield  # application serves requests here

    # Shutdown: stop IMGateway adapters
    try:
        _gw = getattr(app.state, "im_gateway", None)
        if _gw is not None:
            await _gw.stop_all()
            logger.info("prism.im_gateway_shutdown", message="IMGateway stopped.")
    except Exception as exc:
        logger.warning("prism.im_gateway_shutdown_failed", error=str(exc))

    # Shutdown: stop ProcessManager (ADR-066) — kill all subprocesses
    try:
        if getattr(app.state, "process_manager", None) is not None:
            app.state.process_manager.shutdown()
            logger.info("prism.process_manager_shutdown", message="ProcessManager shut down.")
    except Exception as exc:
        logger.warning("prism.process_manager_shutdown_failed", error=str(exc))

    # Shutdown: stop HeartbeatMonitor
    if heartbeat_monitor is not None:
        heartbeat_monitor.stop()
    if heartbeat_task is not None:
        try:
            heartbeat_task.cancel()
            await asyncio.wait_for(heartbeat_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception:
            pass
    # Close dedicated DB session used by heartbeat monitor
    try:
        if heartbeat_monitor is not None and hasattr(_db_for_hb, "close"):
            _db_for_hb.close()
    except Exception:
        pass

    # Shutdown: stop Entropy Detector scheduler
    if entropy_task is not None:
        try:
            entropy_task.cancel()
            await asyncio.wait_for(entropy_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception:
            pass

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

# Structured logging middleware (ADR-118) — binds request_id / user_id to
# structlog contextvars for every HTTP request; cleared after response.
# Must be added *before* CORS so it wraps all requests.
app.add_middleware(StructlogRequestMiddleware)

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
# Health endpoints (ADR-114 / ADR-115 / DOC-12 Task 12.3)
# ---------------------------------------------------------------------------
# Moved to app/api/v1/health.py and registered via api_v1_router at:
#   /api/v1/health/live     — liveness probe (always 200)
#   /api/v1/health/ready    — readiness probe (DB + Redis, 503 on failure)
#   /api/v1/health/detailed — admin-only full report (ResourceMonitor + providers)
#
# For Docker/K8s probes that need a path without the /api/v1 prefix,
# use the top-level aliases below (forwards to the same logic).


@app.get("/health/live", tags=["health"], include_in_schema=False)
async def _health_live_alias() -> dict[str, str]:
    """Top-level alias — delegates to /api/v1/health/live."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
async def _health_ready_alias() -> JSONResponse:
    """Top-level alias — delegates to /api/v1/health/ready logic."""
    import sqlalchemy
    from sqlalchemy import text
    import redis as redis_lib

    checks: dict[str, str] = {}
    overall_ok = True

    try:
        engine = sqlalchemy.create_engine(
            settings.DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        overall_ok = False

    try:
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if overall_ok else "unhealthy", "checks": checks},
    )


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
