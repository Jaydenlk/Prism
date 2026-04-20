"""Session 4b — CredentialCipher Fernet encrypt/decrypt contract (ADR-088 I4)."""
from __future__ import annotations

import pytest

from app.services.credential_cipher import CredentialCipher


def test_encrypt_decrypt_roundtrip() -> None:
    c = CredentialCipher("x" * 32)
    token = c.encrypt("hello-world")
    assert token.startswith("fernet:")
    assert c.decrypt(token) == "hello-world"


def test_plaintext_fallback_returns_as_is() -> None:
    c = CredentialCipher("x" * 32)
    assert c.decrypt("plaintext-legacy") == "plaintext-legacy"


def test_decrypt_with_wrong_key_raises() -> None:
    encryptor = CredentialCipher("key-one" + "0" * 25)
    token = encryptor.encrypt("secret")
    decryptor = CredentialCipher("key-two" + "0" * 25)
    with pytest.raises(ValueError):
        decryptor.decrypt(token)
