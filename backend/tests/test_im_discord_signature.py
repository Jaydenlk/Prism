"""
DOC-IM2 I3 — Discord HTTP Interactions signature verification (Ed25519).

Spec §5.3 + Discord docs: every interaction webhook carries
  X-Signature-Ed25519   — hex of Ed25519(signature)
  X-Signature-Timestamp — UTC timestamp string
Server must verify sig over (timestamp + body) against the application's public
key.  On invalid signature Discord expects non-2xx (spec choice: 401).

PING (type=1) payloads must be answered with PONG (type=1).
"""
from __future__ import annotations

import pytest

pytest.importorskip("nacl", reason="PyNaCl required for Discord Ed25519")

from nacl.signing import SigningKey

from app.services.im_discord import DiscordAdapter


@pytest.fixture
def keypair() -> tuple[SigningKey, str]:
    sk = SigningKey.generate()
    pk_hex = sk.verify_key.encode().hex()
    return sk, pk_hex


def _make_adapter(pk_hex: str) -> DiscordAdapter:
    return DiscordAdapter(
        config={
            "public_key": pk_hex,
            "app_id": "1234567890",
            "bot_token": "MTA-dummy",
        }
    )


def test_valid_signature_passes(keypair: tuple[SigningKey, str]) -> None:
    sk, pk_hex = keypair
    adapter = _make_adapter(pk_hex)
    ts = "1713561600"
    body = b'{"type":1}'
    signed = sk.sign((ts.encode("ascii") + body))
    sig_hex = signed.signature.hex()

    headers = {"X-Signature-Ed25519": sig_hex, "X-Signature-Timestamp": ts}
    assert adapter.verify_signature(headers, body) is True


def test_tampered_body_rejected(keypair: tuple[SigningKey, str]) -> None:
    sk, pk_hex = keypair
    adapter = _make_adapter(pk_hex)
    ts = "1713561600"
    body = b'{"type":1}'
    signed = sk.sign((ts.encode("ascii") + body))
    sig_hex = signed.signature.hex()
    tampered = b'{"type":2}'

    headers = {"X-Signature-Ed25519": sig_hex, "X-Signature-Timestamp": ts}
    assert adapter.verify_signature(headers, tampered) is False


def test_wrong_signature_rejected(keypair: tuple[SigningKey, str]) -> None:
    _, pk_hex = keypair
    adapter = _make_adapter(pk_hex)
    headers = {
        "X-Signature-Ed25519": "00" * 64,  # 64 bytes of zeros — wrong
        "X-Signature-Timestamp": "1",
    }
    assert adapter.verify_signature(headers, b"{}") is False


def test_ping_returns_pong() -> None:
    # PING = type:1 → PONG = type:1.
    adapter = DiscordAdapter(config={"public_key": "00" * 32, "app_id": "1", "bot_token": ""})
    pong = adapter.build_ping_response({"type": 1, "id": "xyz", "application_id": "1"})
    assert pong == {"type": 1}


def test_non_ping_returns_none() -> None:
    # Non-PING interactions are routed to the message handler, not answered here.
    adapter = DiscordAdapter(config={"public_key": "00" * 32, "app_id": "1", "bot_token": ""})
    out = adapter.build_ping_response({"type": 2, "data": {}})
    assert out is None
