from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_raw = os.environ.get("PRISM_BLOCKED_TOOLS", "")
BLOCKED_TOOLS: frozenset[str] = frozenset(t.strip() for t in _raw.split(",") if t.strip())


async def permission_handler(payload: dict) -> dict:
    tool_name = payload.get("tool_name", "")
    if tool_name in BLOCKED_TOOLS:
        logger.warning("permission.blocked", tool=tool_name)
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Tool '{tool_name}' blocked by PRISM_BLOCKED_TOOLS policy",
        }
    return {"continue_": True}
