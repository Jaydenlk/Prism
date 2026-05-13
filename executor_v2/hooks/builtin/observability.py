from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SENSITIVE_KEYS = frozenset({"api_key", "token", "secret", "password", "authorization"})


def _mask_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            masked[k] = "***"
        elif isinstance(v, dict):
            masked[k] = _mask_sensitive(v)
        else:
            masked[k] = v
    return masked


async def observability_handler(payload: dict) -> dict:
    event = payload.get("_event", "unknown")
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    safe_input = _mask_sensitive(payload.get("tool_input", {})) if payload.get("tool_input") else None

    logger.info(
        "hook.event",
        event=event,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        tool_input=safe_input,
    )
    return {"continue_": True}
