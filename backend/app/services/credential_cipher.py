"""
Prism v2 — Credential Cipher (Session 4b, ADR-088 偏离点 #3 / I4)

Fernet (AES-128-CBC + HMAC-SHA256 + timestamp + IV) symmetric encryption for
sensitive values in `im_channel_configs.config` JSONB (and any future
credential-bearing JSONB surface). Uses `settings.ENCRYPTION_KEY` — the third
of Prism's three-key pair (never conflated with JWT_SECRET / CALLBACK_SECRET
per CLAUDE.md 六原则 #5).

Ciphertext format: ``fernet:<urlsafe_base64>``.  The prefix:
  1. lets `decrypt()` fall back to plaintext for legacy values without error;
  2. surfaces encryption state at a glance in DB dumps / admin UI脱敏路径。
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "fernet:"
_SENSITIVE_SUBSTRINGS = ("secret", "token", "key", "password")


class CredentialCipher:
    """Symmetric-key cipher for IM (and future) credential JSONB values."""

    def __init__(self, encryption_key: str) -> None:
        if not encryption_key or len(encryption_key) < 32:
            raise ValueError("encryption_key must be >= 32 chars")
        digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return _PREFIX + token.decode("ascii")

    def decrypt(self, value: str) -> str:
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            return value  # plaintext fallback for legacy values
        try:
            return self._fernet.decrypt(
                value[len(_PREFIX):].encode("ascii")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "ciphertext did not decrypt with configured key"
            ) from exc

    @staticmethod
    def is_encrypted(value: Any) -> bool:
        return isinstance(value, str) and value.startswith(_PREFIX)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(sub in k for sub in _SENSITIVE_SUBSTRINGS)


def encrypt_config_secrets(
    config: dict | None, cipher: CredentialCipher
) -> dict:
    """Return a new dict with sensitive string values encrypted in place.

    Keys whose names contain ``secret`` / ``token`` / ``key`` / ``password``
    (case-insensitive) have their string values encrypted.  Already-encrypted
    values (``fernet:`` prefix) pass through unchanged — makes re-saves
    idempotent.
    """
    out: dict = {}
    for k, v in (config or {}).items():
        if (
            isinstance(v, str)
            and _is_sensitive_key(k)
            and not cipher.is_encrypted(v)
        ):
            out[k] = cipher.encrypt(v)
        else:
            out[k] = v
    return out


def decrypt_config_secrets(
    config: dict | None, cipher: CredentialCipher
) -> dict:
    """Return a new dict with encrypted values decrypted; plaintext passes through.

    Decrypt failures (wrong key / corrupted ciphertext) leave the encrypted
    value in place so operators can triage by inspecting the DB — never
    returns the raw key as plaintext on failure.
    """
    out: dict = {}
    for k, v in (config or {}).items():
        if cipher.is_encrypted(v):
            try:
                out[k] = cipher.decrypt(v)
            except ValueError:
                out[k] = v
        else:
            out[k] = v
    return out
