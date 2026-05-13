from __future__ import annotations

import os
import re

_STATIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*\S+"),
]

_env_secrets: set[str] | None = None


def _load_env_secrets() -> set[str]:
    global _env_secrets
    if _env_secrets is not None:
        return _env_secrets
    _env_secrets = set()
    for key, val in os.environ.items():
        if any(s in key.upper() for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")) and len(val) >= 8:
            _env_secrets.add(val)
    return _env_secrets


def mask(text: str) -> str:
    for val in _load_env_secrets():
        if val in text:
            text = text.replace(val, val[:4] + "***")
    for pat in _STATIC_PATTERNS:
        text = pat.sub(lambda m: m.group()[:6] + "***", text)
    return text


def structlog_masker(logger: object, method: str, event_dict: dict) -> dict:
    for key, val in event_dict.items():
        if isinstance(val, str) and len(val) > 10:
            event_dict[key] = mask(val)
    return event_dict
