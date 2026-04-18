"""
Prism v2 — Alert Dispatcher (DOC-07 Task 7.4, v4)

告警分发服务：按 severity 路由到不同渠道。

Severity 分档规则：
  critical — audit_logs + SSE + IM 群 + Email
  error    — audit_logs + SSE（推送给相关用户）
  warning  — audit_logs
  info     — 仅 structlog（不写 DB）

完整实现说明：
  - IM 群推送在 DOC-08 完成后接入（im_service stub）
  - Email 在 DOC-12 Task 12.8 完整实现（email_service stub）
  - SSE.publish_to_user 已在 Task 7.3 SSEManager 实装
  - 本 Task 实现骨架 + AuditLog 写入 + structlog + SSE 路径
  - im_service / email_service 作为可选依赖传入（None 时跳过）

ADR-066/067 依赖说明：
  AlertDispatcher 由路由层按需实例化，不是 ProcessManager 单例。
  lifespan 无需注册 AlertDispatcher（SSEManager 是单例，DB 是 per-request）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.services.sse_manager import SSEManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "critical"
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

_VALID_SEVERITIES = {SEVERITY_CRITICAL, SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO}


class AlertDispatcher:
    """
    告警分发器（v4 骨架）。

    使用方式（路由层或后台服务中）：
      dispatcher = AlertDispatcher(db, sse_manager, settings)
      await dispatcher.dispatch("error", "run.failed", {"run_id": "..."}, user_id="...")

    IM / Email 服务在 DOC-08 / DOC-12 接入后通过 im_service / email_service 注入。
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
        self._email = email_service

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
        分发告警。

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
                "alert_dispatcher.unknown_severity: severity=%s event_type=%s",
                severity,
                event_type,
            )
            severity = SEVERITY_WARNING

        logger.info(
            "alert_dispatcher.dispatch: severity=%s event_type=%s user_id=%s",
            severity,
            event_type,
            user_id,
        )

        # --- info 级别：仅 structlog，不写 DB ---
        if severity == SEVERITY_INFO:
            return

        # --- warning / error / critical：写 audit_logs ---
        self._write_audit_log(
            action=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            severity=severity,
        )

        # --- error / critical：SSE 推送给相关用户 ---
        if severity in (SEVERITY_ERROR, SEVERITY_CRITICAL) and user_id and self._sse:
            try:
                await self._sse.publish(
                    session_id=f"user:{user_id}",  # 用户级别 SSE channel
                    event_type="alert",
                    data={
                        "severity": severity,
                        "event_type": event_type,
                        "detail": detail,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "alert_dispatcher.sse_publish_failed: severity=%s event_type=%s error=%s",
                    severity,
                    event_type,
                    exc,
                )

        # --- critical：IM 群 + Email ---
        if severity == SEVERITY_CRITICAL:
            await self._send_im_alert(event_type, detail)
            await self._send_email_alert(event_type, detail)

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
                    "_severity": severity,          # 便于查询过滤
                    "_dispatched_at": datetime.now(timezone.utc).isoformat(),
                },
                created_at=datetime.now(timezone.utc),
            )
            self._db.add(log_entry)
            self._db.flush()
            logger.debug(
                "alert_dispatcher.audit_log_written: action=%s severity=%s",
                action,
                severity,
            )
        except Exception as exc:
            logger.error(
                "alert_dispatcher.audit_log_failed: action=%s severity=%s error=%s",
                action,
                severity,
                exc,
            )

    # ------------------------------------------------------------------
    # Internal: IM + Email stubs（DOC-08 / DOC-12 接入）
    # ------------------------------------------------------------------

    async def _send_im_alert(self, event_type: str, detail: dict) -> None:
        """
        IM 群告警（DOC-08 完成后注入 im_service 实例）。

        当前为 stub：仅在 ALERT_IM_CHANNEL 配置时尝试调用。
        """
        alert_channel = getattr(self._settings, "ALERT_IM_CHANNEL", None)
        if not alert_channel:
            logger.debug("alert_dispatcher.im_skipped: ALERT_IM_CHANNEL not configured")
            return

        if self._im is None:
            logger.warning(
                "alert_dispatcher.im_not_available: event_type=%s — IM service not injected",
                event_type,
            )
            return

        try:
            message = f"[CRITICAL] {event_type}: {detail}"
            await self._im.send(alert_channel, message)
            logger.info("alert_dispatcher.im_sent: event_type=%s channel=%s", event_type, alert_channel)
        except Exception as exc:
            logger.error(
                "alert_dispatcher.im_failed: event_type=%s error=%s",
                event_type,
                exc,
            )

    async def _send_email_alert(self, event_type: str, detail: dict) -> None:
        """
        Email 告警（DOC-12 Task 12.8 完整实现）。

        当前为 stub：仅在 ALERT_EMAIL 配置时尝试调用。
        """
        alert_email = getattr(self._settings, "ALERT_EMAIL", None)
        if not alert_email:
            logger.debug("alert_dispatcher.email_skipped: ALERT_EMAIL not configured")
            return

        if self._email is None:
            logger.warning(
                "alert_dispatcher.email_not_available: event_type=%s — Email service not injected",
                event_type,
            )
            return

        try:
            await self._email.send(
                to=alert_email,
                subject=f"[Prism CRITICAL] {event_type}",
                body=str(detail),
            )
            logger.info("alert_dispatcher.email_sent: event_type=%s to=%s", event_type, alert_email)
        except Exception as exc:
            logger.error(
                "alert_dispatcher.email_failed: event_type=%s error=%s",
                event_type,
                exc,
            )
