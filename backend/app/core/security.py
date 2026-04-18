"""
Prism v2 — Security utilities (ADR-004, ADR-050)

This module provides:
  - validate_secrets()        : startup check — three keys must be distinct and >= 32 chars
  - encrypt_value()           : AES-256-GCM encryption (full implementation in DOC-06 v4)
  - decrypt_value()           : AES-256-GCM decryption (full implementation in DOC-06 v4)
  - hash_password()           : bcrypt, cost factor 12
  - verify_password()         : bcrypt comparison
  - create_access_token()     : PyJWT, exp = JWT_ACCESS_TOKEN_EXPIRE_MINUTES
  - create_refresh_token()    : PyJWT, exp = JWT_REFRESH_TOKEN_EXPIRE_DAYS
  - decode_token()            : validate signature + expiry, return payload dict
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Startup secret validation (ADR-004 / ADR-050)
# ---------------------------------------------------------------------------

def validate_secrets(
    jwt_secret: str,
    encryption_key: str,
    callback_secret: str,
) -> None:
    """Validate the three independent secrets required by ADR-004/ADR-050.

    Rules enforced:
      1. Each secret must be at least 32 characters long.
      2. All three secrets must be mutually distinct (no reuse across roles).

    Args:
        jwt_secret:      Value of the JWT_SECRET environment variable.
        encryption_key:  Value of the ENCRYPTION_KEY environment variable.
        callback_secret: Value of the CALLBACK_SECRET environment variable.

    Raises:
        RuntimeError: If any secret is shorter than 32 characters.
        RuntimeError: If any two secrets share the same value.
    """
    named = {
        "JWT_SECRET": jwt_secret,
        "ENCRYPTION_KEY": encryption_key,
        "CALLBACK_SECRET": callback_secret,
    }

    # Rule 1: length >= 32
    for name, value in named.items():
        if len(value) < 32:
            raise RuntimeError(
                f"{name} must be at least 32 characters long "
                f"(got {len(value)} characters). "
                "Generate a safe value with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    # Rule 2: all three must be distinct
    if len(set(named.values())) != 3:
        # Identify which pair(s) collide for a helpful error message.
        pairs = [
            (a_name, b_name)
            for a_name, a_val in named.items()
            for b_name, b_val in named.items()
            if a_name < b_name and a_val == b_val
        ]
        collision_desc = ", ".join(f"{a} == {b}" for a, b in pairs)
        raise RuntimeError(
            f"JWT_SECRET, ENCRYPTION_KEY, and CALLBACK_SECRET must all be different. "
            f"Collisions detected: {collision_desc}"
        )


# ---------------------------------------------------------------------------
# AES-256-GCM envelope encryption (skeleton — full impl in DOC-06 v4)
# ---------------------------------------------------------------------------

def encrypt_value(plaintext: str, key_hex: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM using *key_hex*.

    The ciphertext envelope format is:
        ``<hex-nonce>:<hex-ciphertext+tag>``

    Args:
        plaintext: The UTF-8 string to encrypt (e.g. a provider API key).
        key_hex:   Hex-encoded 32-byte key (i.e. ENCRYPTION_KEY value).
                   Must be exactly 64 hex characters (256 bits).

    Returns:
        A colon-separated string ``"<nonce_hex>:<ciphertext_hex>"`` suitable
        for storage in the database ``config`` JSONB column.

    Raises:
        ValueError: If *key_hex* does not decode to exactly 32 bytes.
    """
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to exactly 32 bytes (256 bits); "
            f"got {len(key_bytes)} bytes."
        )
    nonce = os.urandom(12)  # 96-bit nonce, safe for GCM
    aesgcm = AESGCM(key_bytes)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{nonce.hex()}:{ciphertext.hex()}"


def decrypt_value(envelope: str, key_hex: str) -> str:
    """Decrypt an AES-256-GCM envelope produced by :func:`encrypt_value`.

    Args:
        envelope: The ``"<nonce_hex>:<ciphertext_hex>"`` string as stored in DB.
        key_hex:  Hex-encoded 32-byte key (i.e. ENCRYPTION_KEY value).

    Returns:
        The original plaintext UTF-8 string.

    Raises:
        ValueError: If the envelope format is invalid or the key is wrong length.
        cryptography.exceptions.InvalidTag: If authentication fails (wrong key /
            tampered ciphertext).
    """
    parts = envelope.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            "Invalid encryption envelope format. Expected '<nonce_hex>:<ciphertext_hex>'."
        )
    nonce_hex, ciphertext_hex = parts
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to exactly 32 bytes; got {len(key_bytes)}."
        )
    aesgcm = AESGCM(key_bytes)
    plaintext_bytes = aesgcm.decrypt(
        bytes.fromhex(nonce_hex),
        bytes.fromhex(ciphertext_hex),
        None,
    )
    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash *password* with bcrypt at cost factor 12.

    Args:
        password: The plain-text password to hash.

    Returns:
        A bcrypt hash string safe for storage in the ``users.password_hash`` column.
    """
    import bcrypt  # lazy import — only needed for auth paths

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify *plain* against a bcrypt *hashed* value.

    Args:
        plain:  The plain-text password provided by the user.
        hashed: The stored bcrypt hash (from ``users.password_hash``).

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    import bcrypt

    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    """Create a short-lived JWT access token for *user_id*.

    Args:
        user_id: The UUID string of the authenticated user.

    Returns:
        A signed JWT string with ``exp`` set to
        ``now + JWT_ACCESS_TOKEN_EXPIRE_MINUTES`` minutes.
    """
    from jose import jwt

    from app.core.config import settings

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(tz=timezone.utc)
        + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived JWT refresh token for *user_id*.

    Args:
        user_id: The UUID string of the authenticated user.

    Returns:
        A signed JWT string with ``exp`` set to
        ``now + JWT_REFRESH_TOKEN_EXPIRE_DAYS`` days.
    """
    from jose import jwt

    from app.core.config import settings

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(tz=timezone.utc)
        + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT *token*.

    Args:
        token: A JWT string (access or refresh).

    Returns:
        The decoded payload dictionary (contains ``sub``, ``type``, ``exp``).

    Raises:
        jose.JWTError: If the signature is invalid, the token is expired, or
            the token is otherwise malformed.
    """
    from jose import jwt

    from app.core.config import settings

    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
