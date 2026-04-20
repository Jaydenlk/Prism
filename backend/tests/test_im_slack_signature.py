"""
DOC-IM2 I2 — Slack Events API signature verification (HMAC-SHA256 with v0: prefix).

Spec §5.3 + Slack docs:
  base = "v0:{ts}:{body}"
  expected = "v0=" + hmac_sha256(signing_secret, base).hexdigest()

The adapter must:
  - accept valid signature within a ±5 minute timestamp window
  - reject signatures whose timestamp is outside the window (replay attacks)
  - reject tampered bodies
"""
from __future__ import annotations

import hmac
import hashlib
import time

from app.services.im_slack import SlackAdapter


SIGNING_SECRET = "8f742231b10e8888abcd99yyyzzz85ed"


def _sign(body: bytes, ts: str) -> str:
    base = b"v0:" + ts.encode("ascii") + b":" + body
    digest = hmac.new(SIGNING_SECRET.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _make_adapter() -> SlackAdapter:
    return SlackAdapter(
        config={
            "signing_secret": SIGNING_SECRET,
            "bot_token": "xoxb-test-123",
            "app_token": "",
            "mode": "events",
        }
    )


def test_valid_signature_passes() -> None:
    adapter = _make_adapter()
    body = b'{"type":"event_callback","event":{"type":"message","text":"hi"}}'
    ts = str(int(time.time()))
    sig = _sign(body, ts)

    headers = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}
    assert adapter.verify_signature(headers, body) is True


def test_tampered_body_rejected() -> None:
    adapter = _make_adapter()
    body = b'{"type":"event_callback","event":{"type":"message","text":"hi"}}'
    ts = str(int(time.time()))
    sig = _sign(body, ts)
    tampered = body.replace(b"hi", b"bye")

    headers = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}
    assert adapter.verify_signature(headers, tampered) is False


def test_expired_timestamp_rejected() -> None:
    # Older than 5 minutes → reject replay.
    adapter = _make_adapter()
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()) - 600)
    sig = _sign(body, ts)

    headers = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}
    assert adapter.verify_signature(headers, body) is False


def test_future_timestamp_rejected() -> None:
    # Well into the future → reject.
    adapter = _make_adapter()
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()) + 600)
    sig = _sign(body, ts)

    headers = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}
    assert adapter.verify_signature(headers, body) is False


def test_url_verification_challenge() -> None:
    # Slack's one-time URL verification handshake.  Body: {"type":"url_verification","challenge":"..."}
    adapter = _make_adapter()
    body = b'{"type":"url_verification","challenge":"abc123"}'
    resp = adapter.build_url_verification_response(body)
    assert resp == {"challenge": "abc123"}
