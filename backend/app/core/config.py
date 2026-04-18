"""
Prism v2 — Application Settings (ADR-004, ADR-005)

All configuration is read from environment variables.  A single Settings
instance is cached via @lru_cache so the same object is shared across the
whole process lifetime.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    PRISM_ENV: str = "development"

    # --- Database ----------------------------------------------------------
    DATABASE_URL: str = "postgresql://prism:prism_dev_pass@postgres:5432/prism_dev"

    # --- Redis -------------------------------------------------------------
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Three Independent Secrets (ADR-004 / ADR-050) --------------------
    # Each must be >= 32 chars and all three must differ.
    # validate_secrets() in security.py enforces this at startup.
    JWT_SECRET: str
    ENCRYPTION_KEY: str
    CALLBACK_SECRET: str

    # --- JWT Expiry --------------------------------------------------------
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Admin bootstrap --------------------------------------------------
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "change_me_in_production"

    # --- Run / Harness limits ---------------------------------------------
    MAX_CONCURRENT_RUNS: int = 2
    RUN_TIMEOUT_SECONDS: int = 600
    MAX_TURNS_PER_RUN: int = 50          # Harness turn-count cap
    LOOP_DETECTION_WINDOW: int = 5       # Harness loop-detection look-back

    # --- Permission Ask / Hook timeouts (Task 3.3, ADR-028) ---------------
    PERMISSION_ASK_TIMEOUT_SECONDS: int = 300  # fail-safe deny 超时
    HOOK_TIMEOUT_SECONDS: int = 10             # 单个 Hook handler 超时
    RATE_LIMIT_WINDOW_SECONDS: int = 60        # 速率限制窗口
    RATE_LIMIT_DEFAULT: int = 30               # 默认速率上限（次/窗口）

    # --- Circuit Breaker (Provider failover) ------------------------------
    CIRCUIT_BREAKER_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300

    # --- Heartbeat / SSE --------------------------------------------------
    HEARTBEAT_INTERVAL_SECONDS: int = 15
    SSE_TICKET_TTL_SECONDS: int = 60

    # --- Observability ----------------------------------------------------
    PROMETHEUS_METRICS_ENABLED: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "prism-backend"

    # --- Alert Dispatcher (ADR-120) ---------------------------------------
    # IM 群告警：格式 "{platform}:{chat_id}"，如 "feishu:oc_xxx"
    ALERT_IM_CHANNEL: str = ""
    # Email 告警收件人（逗号分隔多个）
    ALERT_EMAIL: str = ""
    # SMTP 配置（Phase 1，未配置时 email 告警降级）
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@prism.local"
    # 告警详情页 base URL（用于 IM 消息链接）
    PRISM_BASE_URL: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


# Module-level alias used throughout the codebase.
settings: Settings = get_settings()
