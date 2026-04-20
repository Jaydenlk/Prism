"""Session 4b — IM credential encryption helper contract (ADR-088 I4).

Backed by app.core.security (AES-256-GCM) — we verify the prefix routing,
roundtrip, plaintext fallback, and sensitive-key scrubbing policy here; the
underlying cipher is already covered by provider_service tests.
"""
from __future__ import annotations

import pytest

from app.services.credential_cipher import (
    decrypt_config_secrets,
    decrypt_str,
    encrypt_config_secrets,
    encrypt_str,
    is_encrypted,
)

# 32-byte hex test key (matches ENCRYPTION_KEY format from .env/settings)
_TEST_KEY = "a" * 64
_OTHER_KEY = "b" * 64


def test_encrypt_decrypt_roundtrip() -> None:
    token = encrypt_str("hello-world", _TEST_KEY)
    assert token.startswith("aesgcm:")
    assert is_encrypted(token)
    assert decrypt_str(token, _TEST_KEY) == "hello-world"


def test_plaintext_fallback_returns_as_is() -> None:
    assert decrypt_str("plaintext-legacy", _TEST_KEY) == "plaintext-legacy"
    assert is_encrypted("plaintext-legacy") is False


def test_decrypt_with_wrong_key_raises() -> None:
    token = encrypt_str("secret", _TEST_KEY)
    with pytest.raises(ValueError):
        decrypt_str(token, _OTHER_KEY)


def test_encrypt_config_secrets_scrubs_only_sensitive_keys() -> None:
    config = {
        "app_id": "cli_public_id",
        "bot_token": "xoxb-secret-123",
        "signing_secret": "sig-secret",
        "mode": "events",
    }
    encrypted = encrypt_config_secrets(config, _TEST_KEY)
    # Public keys pass through
    assert encrypted["app_id"] == "cli_public_id"
    assert encrypted["mode"] == "events"
    # Sensitive keys get encrypted
    assert is_encrypted(encrypted["bot_token"])
    assert is_encrypted(encrypted["signing_secret"])
    # Roundtrip via decrypt_config_secrets
    decrypted = decrypt_config_secrets(encrypted, _TEST_KEY)
    assert decrypted == config


def test_encrypt_config_secrets_idempotent_on_already_encrypted() -> None:
    once = encrypt_config_secrets({"bot_token": "xoxb-1"}, _TEST_KEY)
    twice = encrypt_config_secrets(once, _TEST_KEY)
    # Second encrypt must be a no-op (same ciphertext string preserved)
    assert once["bot_token"] == twice["bot_token"]
