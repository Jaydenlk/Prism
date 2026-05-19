"""
Prism v2 — EmailService

Sends transactional emails. Three modes (checked in order):

1. RESEND_API_KEY set → Resend HTTP API (POST https://api.resend.com/emails)
2. SMTP_HOST set → smtplib + STARTTLS (port 587)
3. Neither → logger.info("email.dev_log") — body visible in docker logs
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.core.config import Settings

logger = structlog.get_logger()


class EmailService:
    """Send transactional emails; degrades gracefully when unconfigured."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._resend_key = settings.RESEND_API_KEY or ""
        self._smtp_configured = bool(settings.SMTP_HOST)

    def send(self, *, to: str, subject: str, body: str) -> None:
        if self._resend_key:
            self._send_resend(to=to, subject=subject, body=body)
        elif self._smtp_configured:
            self._send_smtp(to=to, subject=subject, body=body)
        else:
            logger.info("email.dev_log", to=to, subject=subject, body=body)

    def _send_resend(self, *, to: str, subject: str, body: str) -> None:
        try:
            payload = json.dumps(
                {
                    "from": self._settings.SMTP_FROM,
                    "to": to,
                    "subject": subject,
                    "html": f'<div style="font-family:sans-serif;font-size:15px;">{body}</div>',
                },
                ensure_ascii=False,
            ).encode("utf-8")

            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._resend_key}",
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "Prism/2.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            logger.info("email.sent.resend", to=to, subject=subject, resend_id=result.get("id"))

        except Exception as exc:
            logger.error("email.send_failed.resend", to=to, subject=subject, error=str(exc))

    def _send_smtp(self, *, to: str, subject: str, body: str) -> None:
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

            logger.info("email.sent.smtp", to=to, subject=subject)

        except Exception as exc:
            logger.error("email.send_failed.smtp", to=to, subject=subject, error=str(exc))
