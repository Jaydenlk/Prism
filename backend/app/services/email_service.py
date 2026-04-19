"""
Prism v2 — EmailService

Sends transactional emails via SMTP.

SMTP configured detection: bool(settings.SMTP_HOST)
  - Configured → send real email via smtplib + STARTTLS (port 587)
  - Not configured → logger.info("email.dev_log", ...) — body visible in docker logs

On startup, if SMTP_HOST is empty, logs a warning ("auth.email_dev_mode") once.
This warning is emitted by the caller (lifespan/startup), not here.

Usage:
    svc = EmailService(settings)
    await svc.send(to="user@example.com", subject="Login Link", body="...")
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.core.config import Settings

logger = structlog.get_logger()


class EmailService:
    """Send transactional emails; degrades gracefully when SMTP is unconfigured."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._configured = bool(settings.SMTP_HOST)

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send an email (or log it in dev mode).

        Args:
            to:      Recipient email address.
            subject: Email subject line.
            body:    Plain-text email body.
        """
        if not self._configured:
            # Dev-mode degradation — log the full content so developer can read it
            logger.info(
                "email.dev_log",
                to=to,
                subject=subject,
                body=body,
            )
            return

        # --- SMTP send --------------------------------------------------------
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._settings.SMTP_FROM
            msg["To"] = to
            msg.attach(MIMEText(body, "plain", "utf-8"))

            context = ssl.create_default_context()
            with smtplib.SMTP(
                self._settings.SMTP_HOST, self._settings.SMTP_PORT
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                if self._settings.SMTP_USER:
                    server.login(
                        self._settings.SMTP_USER, self._settings.SMTP_PASSWORD
                    )
                server.sendmail(self._settings.SMTP_FROM, to, msg.as_string())

            logger.info("email.sent", to=to, subject=subject)

        except Exception as exc:
            # Never raise — email failure should not block auth flow
            logger.error(
                "email.send_failed",
                to=to,
                subject=subject,
                error=str(exc),
            )
