"""
DOC-IM2 I1 — Feishu card callback signature (SHA-1 path).

Spec §5.4: `verify_card_signature(headers, body) -> bool` using
  SHA-1(timestamp + nonce + verification_token + body).hexdigest()

These tests pin the exact algorithm against a known-good fixture.  Event-
subscription (SHA-256) path is covered separately by test_feishu_webhook.py;
here we verify the distinct card path and confirm they don't cross-wire.
"""
from __future__ import annotations

import hashlib

from app.services.im_feishu import FeishuAdapter


def _make_adapter() -> FeishuAdapter:
    return FeishuAdapter(
        config={
            "app_id": "cli_a1b2c3d4",
            "app_secret": "dummy_secret",
            "encrypt_key": "encrypt_key_abc",
            "verify_token": "verify_token_xyz",
        }
    )


def _card_signature(timestamp: str, nonce: str, verification_token: str, body_bytes: bytes) -> str:
    content = (timestamp + nonce + verification_token).encode("utf-8") + body_bytes
    return hashlib.sha1(content).hexdigest()


def test_verify_card_signature_happy_path() -> None:
    adapter = _make_adapter()
    ts = "1713561600"
    nonce = "n7f3a2c1"
    body = b'{"action":{"tag":"button","value":{"op":"confirm"}}}'
    sig = _card_signature(ts, nonce, "verify_token_xyz", body)

    headers = {
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": sig,
    }
    assert adapter.verify_card_signature(headers, body) is True


def test_verify_card_signature_rejects_tampered_body() -> None:
    adapter = _make_adapter()
    ts = "1713561600"
    nonce = "n7f3a2c1"
    body = b'{"action":{"value":{"op":"confirm"}}}'
    sig = _card_signature(ts, nonce, "verify_token_xyz", body)
    tampered = b'{"action":{"value":{"op":"malicious"}}}'

    headers = {
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": sig,
    }
    assert adapter.verify_card_signature(headers, tampered) is False


def test_verify_card_signature_rejects_wrong_token() -> None:
    # Simulates a verify_token mismatch (caller config drift or attacker guess)
    adapter = _make_adapter()
    ts = "1713561600"
    nonce = "n7f3a2c1"
    body = b'{"action":{"value":{"op":"confirm"}}}'
    wrong_sig = _card_signature(ts, nonce, "other_token", body)

    headers = {
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": wrong_sig,
    }
    assert adapter.verify_card_signature(headers, body) is False


def test_verify_card_signature_fails_without_token() -> None:
    # Adapter without verification_token configured: security-fail-closed.
    adapter = FeishuAdapter(config={"app_id": "x", "app_secret": "y", "encrypt_key": "z", "verify_token": ""})
    headers = {
        "X-Lark-Request-Timestamp": "1",
        "X-Lark-Request-Nonce": "n",
        "X-Lark-Signature": "deadbeef",
    }
    assert adapter.verify_card_signature(headers, b"{}") is False


def test_event_signature_path_still_works() -> None:
    # Regression: SHA-256 event path must still verify its own payload.
    # (Uses encrypt_key, not verification_token; distinct from card path.)
    adapter = _make_adapter()
    ts = "1713561600"
    nonce = "event_nonce"  # nonce is part of X-Lark headers but not SHA-256 content
    body = b'{"type":"event_callback","event":{"type":"im.message.receive_v1"}}'
    content = (ts + "encrypt_key_abc").encode("utf-8") + body
    sig = hashlib.sha256(content).hexdigest()
    assert adapter.verify_signature(ts, nonce, body, sig) is True
