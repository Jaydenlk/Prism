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

    # --- LLM Provider API Keys (default seeds for scope=system providers) -
    # Admin 可在 UI 中调整；用户可在个人设置中 override (scope=user)。
    # 空值 → 留 SYSTEM_PRESET_NO_KEY 占位，需要手动配置才能使用该 Provider。
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_MODEL_ID: str = ""    # optional override; empty → preset's default model_id
    LLM_REQUEST_TIMEOUT_SECONDS: int = 300  # upstream model HTTP timeout
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimaxi.com/anthropic"
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    GLM_API_KEY: str = ""
    GLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    # --- Executor / Callback URL -------------------------------------------
    BACKEND_URL: str = "http://backend:8000"

    # --- Google OAuth (Task B) --------------------------------------------
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8080/api/v1/auth/google/callback"
    FRONTEND_BASE_URL: str = "http://localhost:8080"

    # --- Feishu (Lark) IM Bot (Task B-1) ---------------------------------
    # Register at https://open.feishu.cn/app → 事件订阅 → 请求URL配置
    # Leave all blank to disable Feishu bot (webhook returns 503).
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_ENCRYPT_KEY: str = ""
    FEISHU_VERIFICATION_TOKEN: str = ""
    FEISHU_MODE: str = "webhook"  # "websocket" or "webhook"

    # --- Slack IM Bot (DOC-IM2 I2, ADR-088) -------------------------------
    # Create app at https://api.slack.com/apps; Signing Secret from Basic
    # Information, Bot Token from OAuth & Permissions (xoxb-...).
    # IM_SLACK_MODE=events uses HTTP Events API + /im/webhook/slack;
    # IM_SLACK_MODE=socket uses Socket Mode with xapp-... app-level token.
    SLACK_SIGNING_SECRET: str = ""
    SLACK_BOT_TOKEN: str = ""
    SLACK_APP_TOKEN: str = ""
    IM_SLACK_MODE: str = "events"  # events | socket

    # --- Discord IM Bot (DOC-IM2 I3, ADR-088) -----------------------------
    # From https://discord.com/developers/applications → <app> → General
    # Information (Public Key, Application ID) + Bot (Bot Token).
    DISCORD_PUBLIC_KEY: str = ""  # hex Ed25519 pubkey (64 chars)
    DISCORD_APP_ID: str = ""
    DISCORD_BOT_TOKEN: str = ""

    # --- WeCom / 企业微信 IM Bot (DOC-IM2) --------------------------------
    WECOM_CORP_ID: str = ""
    WECOM_TOKEN: str = ""
    WECOM_ENCODING_AES_KEY: str = ""
    WECOM_AGENT_ID: str = ""
    WECOM_SECRET: str = ""

    # --- Telegram Bot (DOC-IM2) -------------------------------------------
    TELEGRAM_BOT_TOKEN: str = ""

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
