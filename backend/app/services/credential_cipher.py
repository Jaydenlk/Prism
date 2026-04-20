"""
Prism v2 — IM credential field-level encryption helpers (Session 4b, ADR-088 I4).

Thin wrapper over ``app.core.security.encrypt_value`` / ``decrypt_value``
(AES-256-GCM with ``settings.ENCRYPTION_KEY``, 64-hex, 32-byte key, per
Provider API-key encryption pattern). The wrapper adds:

  1. ``aesgcm:`` prefix so encrypted JSONB values are distinguishable from
     plaintext ones in mixed configs (legacy plaintext from env/.env remain
     valid, new PATCH writes produce ciphertext).
  2. A sensitive-key predicate so callers (im.py PATCH) can encrypt only the
     fields whose names contain ``secret / token / key / password``.

This file exists as a façade so call-sites do not reach into crypto internals
directly and the IM-specific scrubbing policy lives in one place. Encryption
itself is **not reimplemented** — CLAUDE.md 六原则 #1 单一职责。
"""
from __future__ import annotations

from typing import Any

from app.core.security import decrypt_value as _decrypt
from app.core.security import encrypt_value as _encrypt

_PREFIX = "aesgcm:"
_SENSITIVE_SUBSTRINGS = ("secret", "token", "key", "password")


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_str(plaintext: str, key_hex: str) -> str:
    return _PREFIX + _encrypt(plaintext, key_hex)


def decrypt_str(envelope: str, key_hex: str) -> str:
    """Decrypt ``aesgcm:<envelope>``; returns plaintext pass-through for
    legacy values without the prefix."""
    if not is_encrypted(envelope):
        return envelope
    try:
        return _decrypt(envelope[len(_PREFIX):], key_hex)
    except Exception as exc:  # InvalidTag / ValueError / etc
        raise ValueError(
            "ciphertext did not decrypt with configured ENCRYPTION_KEY"
        ) from exc


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(sub in k for sub in _SENSITIVE_SUBSTRINGS)


def encrypt_config_secrets(config: dict | None, key_hex: str) -> dict:
    """Return a new dict with sensitive string values encrypted in place.

    Already-encrypted values (``aesgcm:`` prefix) pass through unchanged,
    making re-saves idempotent and safe.
    """
    out: dict = {}
    for k, v in (config or {}).items():
        if (
            isinstance(v, str)
            and _is_sensitive_key(k)
            and not is_encrypted(v)
        ):
            out[k] = encrypt_str(v, key_hex)
        else:
            out[k] = v
    return out


def decrypt_config_secrets(config: dict | None, key_hex: str) -> dict:
    """Return a new dict with encrypted values decrypted; plaintext pass-through.

    Decrypt failures (wrong key / corrupted ciphertext) leave the encrypted
    value in place so operators can triage by inspecting the DB — never
    returns the raw key as plaintext on failure.
    """
    out: dict = {}
    for k, v in (config or {}).items():
        if is_encrypted(v):
            try:
                out[k] = decrypt_str(v, key_hex)
            except ValueError:
                out[k] = v
        else:
            out[k] = v
    return out
