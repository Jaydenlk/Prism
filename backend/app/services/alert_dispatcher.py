"""
Prism v2 — Alert Dispatcher (DOC-07 Task 7.4 skeleton → DOC-12 Task 12.8 full, ADR-120)

告警分发服务：按 severity 路由到不同渠道。

ADR-120 Severity 分档规则：
  info     — 仅 structlog（不写 audit）
  warning  — audit_logs
  error    — audit_logs + 用户 SSE alert 事件（若 user_id 可推）
  critical — 上述 + IM 群告警（admin 配置 ALERT_IM_CHANNEL）+ email（可选）

IM 告警：
  - 复用 DOC-08 v4 IM Gateway，不新造 IM 适配器
  - 消息体含 event_type + detail preview + 告警详情页链接（Markdown 格式）
  - admin 配置的 ALERT_IM_CHANNEL 生效

Email 告警（Phase 1 SMTP）：
  - 未配置 SMTP 时降级：仅写 audit_logs（fail-open）
  - SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / ALERT_EMAIL 通过 Settings 注入

降级策略（critical 级别）：
  任何通道失败不影响其他通道（try/except 独立处理）
  全部降级时至少保证 audit_logs 写入成功

三触发点（PRD Part B §4-6）：
  1. EntropyDetector  → dispatch("error"/"critical", "harness.entropy_alert", ...)
  2. HeartbeatMonitor → dispatch("critical", "run.crashed", ...)
  3. ResourceMonitor  → dispatch("warning"/"critical", "resource.memory", ...)
"""
from __future__ import annotations

import logging
import smtplib
import textwrap
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.services.sse_manager import SSEManager

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "critical"
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

_VALID_SEVERITIES = {SEVERITY_CRITICAL, SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO}

# ---------------------------------------------------------------------------
# IM message formatter (ADR-120)
# ---------------------------------------------------------------------------


def _format_im_message(event_type: str, detail: dict, severity: str, base_url: str = "") -> str:
    """
    Markdown 格式 IM 告警消息体。

    格式::

        🚨 [CRITICAL] Prism Alert
        **事件类型**: run.crashed
        **时间**: 2026-04-19 12:00:00 UTC
        **详情**:
        > run_id: abc123
        > reason: heartbeat_stale_35s

        [查看告警详情](https://prism.example.com/admin/alerts/harness.entropy_alert)
    """
    severity_emoji = {
        SEVERITY_CRITICAL: "🚨",
        SEVERITY_ERROR: "❗",
        SEVERITY_WARNING: "⚠️",
        SEVERITY_INFO: "ℹ️",
    }.get(severity, "📢")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # detail preview: first 3 key-value pairs, truncated
    detail_lines: list[str] = []
    for i, (k, v) in enumerate(detail.items()):
        if i >= 3:
            break
        v_str = str(v)
        if len(v_str) > 80:
            v_str = v_str[:77] + "..."
        detail_lines.append(f"> {k}: {v_str}")

    detail_preview = "\n".join(detail_lines) if detail_lines else "> (无额外详情)"

    # alert detail page link
    alert_link = ""
    if base_url:
        alert_link = f"\n\n[查看告警详情]({base_url}/admin/alerts/{event_type})"

    message = textwrap.dedent(f"""\
        {severity_emoji} **[{severity.upper()}] Prism Alert**
        **事件类型**: {event_type}
        **时间**: {now_str}
        **详情**:
        {detail_preview}{alert_link}
    """).strip()

    return message


# ---------------------------------------------------------------------------
# Email service (Phase 1 SMTP)
# ---------------------------------------------------------------------------


class EmailService:
    """
    Phase 1 SMTP email 发送器。

    配置项（Settings）：
      SMTP_HOST     — SMTP 服务器地址（空字符串 = 禁用）
      SMTP_PORT     — 端口（默认 587，STARTTLS）
      SMTP_USER     — SMTP 用户名（可选）
      SMTP_PASSWORD — SMTP 密码（可选）
      ALERT_EMAIL   — 告警收件人地址（逗号分隔多个）

    未配置时降级：仅记录 structlog，不抛出异常。
    """

    def __init__(self, settings: "Settings") -> None:
        self._host: str = getattr(settings, "SMTP_HOST", "") or ""
        self._port: int = int(getattr(settings, "SMTP_PORT", 587) or 587)
        self._user: str = getattr(settings, "SMTP_USER", "") or ""
        self._password: str = getattr(settings, "SMTP_PASSWORD", "") or ""
        self._from_addr: str = getattr(settings, "SMTP_FROM", "noreply@prism.local") or "noreply@prism.local"
        self._alert_email: str = getattr(settings, "ALERT_EMAIL", "") or ""

    @property
    def is_configured(self) -> bool:
        return bool(self._host and self._alert_email)

    def send_alert(self, event_type: str, detail: dict, severity: str) -> None:
        """
        发送告警邮件（同步 SMTP，在 async 上下文中以 run_in_executor 调用）。

        降级策略：任何 SMTP 异常都 catch 并记录 warning，不重新抛出。
        """
        if not self.is_configured:
            logger.debug(
                "email_service.skipped",
                reason="SMTP not configured",
                event_type=event_type,
            )
            return

        subject = f"[Prism {severity.upper()}] {event_type}"

        # Plain text body
        lines = [f"Prism Alert — {severity.upper()}", f"Event: {event_type}", ""]
        for k, v in detail.items():
            v_str = str(v)[:200]
            lines.append(f"  {k}: {v_str}")
        lines.append("")
        lines.append(f"Dispatched at: {datetime.now(timezone.utc).isoformat()}")
        body = "\n".join(lines)

        recipients = [r.strip() for r in self._alert_email.split(",") if r.strip()]
        if not recipients:
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from_addr
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.sendmail(self._from_addr, recipients, msg.as_string())
            logger.info(
                "email_service.sent",
                event_type=event_type,
                severity=severity,
                recipients=recipients,
            )
        except Exception as exc:
            logger.warning(
                "email_service.failed",
                event_type=event_type,
                severity=severity,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# AlertDispatcher (ADR-120 — full implementation)
# ---------------------------------------------------------------------------


class AlertDispatcher:
    """
    告警分发器（ADR-120 完整实现）。

    使用方式（路由层或后台服务中）::

        dispatcher = AlertDispatcher(db, sse_manager, settings)
        await dispatcher.dispatch("critical", "run.crashed", {"run_id": "..."})

    三触发点接入（PRD Part B §4-6）：
      - EntropyDetector.detect()          → dispatch("error"/"critical", "harness.entropy_alert", ...)
      - HeartbeatMonitor._handle_key()    → dispatch("critical", "run.crashed", ...)
      - ResourceMonitor.check_health()    → dispatch("warning"/"critical", "resource.memory", ...)

    IM 告警复用 DOC-08 IMGateway（im_service 注入，None 时跳过）。
    Email 告警通过内置 EmailService（Settings.SMTP_HOST 未配置时降级）。
    """

    def __init__(
        self,
        db: "Session",
        sse_manager: "SSEManager | None",
        settings: "Settings",
        im_service: Any = None,
        email_service: Any = None,
    ) -> None:
        self._db = db
        self._sse = sse_manager
        self._settings = settings
        self._im = im_service
        # email_service 可外部注入（测试 mock）或自动从 settings 构建
        if email_service is None:
            email_service = EmailService(settings)
        self._email: EmailService = email_service
        self._base_url: str = getattr(settings, "PRISM_BASE_URL", "") or ""

    async def dispatch(
        self,
        severity: str,
        event_type: str,
        detail: dict,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        """
        按 severity 分档分发告警（ADR-120）。

        Args:
            severity:      "critical" | "error" | "warning" | "info"
            event_type:    dot-namespaced 事件类型（如 "run.crashed"）
            detail:        告警详情 dict（存入 audit_logs.details）
            user_id:       关联用户 ID（可选；SSE 推送目标）
            resource_type: 关联资源类型（可选；写入 audit_logs）
            resource_id:   关联资源 ID（可选；写入 audit_logs）
        """
        if severity not in _VALID_SEVERITIES:
            logger.warning(
                "alert_dispatcher.unknown_severity",
                severity=severity,
                event_type=event_type,
            )
            severity = SEVERITY_WARNING

        logger.info(
            "alert_dispatcher.dispatch",
            severity=severity,
            event_type=event_type,
            user_id=user_id,
        )

        # ── info：仅 structlog，不写 DB（ADR-120）────────────────────────────
        if severity == SEVERITY_INFO:
            return

        # ── warning / error / critical：写 audit_logs（ADR-120）────────────
        self._write_audit_log(
            action=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            severity=severity,
        )

        # ── error / critical：SSE 推送给相关用户（ADR-120）───────────────────
        if severity in (SEVERITY_ERROR, SEVERITY_CRITICAL) and user_id and self._sse:
            try:
                await self._sse.publish(
                    session_id=f"user:{user_id}",
                    event_name="alert",
                    data={
                        "severity": severity,
                        "event_type": event_type,
                        "detail": detail,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "alert_dispatcher.sse_publish_failed",
                    severity=severity,
                    event_type=event_type,
                    error=str(exc),
                )

        # ── critical：IM 群 + Email（ADR-120）────────────────────────────────
        if severity == SEVERITY_CRITICAL:
            await self._send_im_alert(event_type, detail, severity)
            self._send_email_alert_sync(event_type, detail, severity)

    # ------------------------------------------------------------------
    # Internal: audit_logs write
    # ------------------------------------------------------------------

    def _write_audit_log(
        self,
        action: str,
        user_id: str | None,
        resource_type: str | None,
        resource_id: str | None,
        detail: dict,
        severity: str,
    ) -> None:
        """
        写入 audit_logs 表。

        severity 存储在 details dict 中（audit_logs 表无独立 severity 列）。
        """
        from app.models.audit import AuditLog

        try:
            log_entry = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details={
                    **detail,
                    "_severity": severity,
                    "_dispatched_at": datetime.now(timezone.utc).isoformat(),
                },
                created_at=datetime.now(timezone.utc),
            )
            self._db.add(log_entry)
            self._db.flush()
            logger.debug(
                "alert_dispatcher.audit_log_written",
                action=action,
                severity=severity,
            )
        except Exception as exc:
            logger.error(
                "alert_dispatcher.audit_log_failed",
                action=action,
                severity=severity,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal: IM 群告警（ADR-120）
    # ------------------------------------------------------------------

    async def _send_im_alert(self, event_type: str, detail: dict, severity: str) -> None:
        """
        IM 群告警（复用 DOC-08 IM Gateway，不新造适配器）。

        ALERT_IM_CHANNEL 格式："{platform}:{chat_id}"
          例："feishu:oc_xxx" / "telegram:-100123456789" / "wecom:gr_xxx"
        """
        alert_channel = getattr(self._settings, "ALERT_IM_CHANNEL", None) or ""
        if not alert_channel:
            logger.debug(
                "alert_dispatcher.im_skipped",
                reason="ALERT_IM_CHANNEL not configured",
                event_type=event_type,
            )
            return

        if self._im is None:
            logger.warning(
                "alert_dispatcher.im_not_available",
                event_type=event_type,
                reason="IM service not injected",
            )
            return

        try:
            message = _format_im_message(event_type, detail, severity, self._base_url)

            # im_service 可为 IMGateway 实例或任何实现 send_text(channel, chat_id, text) 的对象
            # 尝试两种接口：send_text(channel, chat_id, text) 或 send(channel, text)
            if ":" in alert_channel:
                platform, chat_id = alert_channel.split(":", 1)
                if hasattr(self._im, "send_text"):
                    await self._im.send_text(platform, chat_id, message)
                elif hasattr(self._im, "send"):
                    await self._im.send(alert_channel, message)
                else:
                    logger.warning(
                        "alert_dispatcher.im_interface_unknown",
                        event_type=event_type,
                        im_type=type(self._im).__name__,
                    )
                    return
            else:
                # fallback: 直接调用 send(channel, text)
                if hasattr(self._im, "send"):
                    await self._im.send(alert_channel, message)

            logger.info(
                "alert_dispatcher.im_sent",
                event_type=event_type,
                channel=alert_channel,
                severity=severity,
            )
        except Exception as exc:
            logger.error(
                "alert_dispatcher.im_failed",
                event_type=event_type,
                severity=severity,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal: Email 告警（Phase 1 SMTP，ADR-120）
    # ------------------------------------------------------------------

    def _send_email_alert_sync(self, event_type: str, detail: dict, severity: str) -> None:
        """
        同步 SMTP email 告警（Phase 1）。

        未配置时降级：仅记录 debug，不抛出。
        """
        try:
            self._email.send_alert(event_type, detail, severity)
        except Exception as exc:
            logger.error(
                "alert_dispatcher.email_unexpected_error",
                event_type=event_type,
                severity=severity,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Admin alert config schema (for PATCH /admin/alerts/config)
# ---------------------------------------------------------------------------

class AlertConfig:
    """
    告警配置（写入 Settings / 环境变量）。

    持久化策略：
      Phase 1 — Settings 字段优先（启动时读 .env）
      Admin PATCH 端点将更新 .env 文件（如存在）或仅在内存中生效（重启失效）。
    """

    FIELDS = {
        "alert_im_channel": "ALERT_IM_CHANNEL",
        "alert_email": "ALERT_EMAIL",
        "smtp_host": "SMTP_HOST",
        "smtp_port": "SMTP_PORT",
        "smtp_user": "SMTP_USER",
        "smtp_from": "SMTP_FROM",
        "prism_base_url": "PRISM_BASE_URL",
    }
