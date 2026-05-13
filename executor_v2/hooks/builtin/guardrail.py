from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

INVESTMENT_KEYWORDS: frozenset[str] = frozenset({
    "投资", "理财", "炒股", "基金推荐", "股票推荐",
    "buy stock", "investment advice",
})

WORKSPACE_PREFIX = os.environ.get("WORKSPACE_PATH", "/workspace")


async def pre_guardrail(payload: dict) -> dict:
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path", "command"):
        value = str(tool_input.get(key, ""))
        if not value:
            continue
        resolved = os.path.realpath(value)
        if not resolved.startswith(WORKSPACE_PREFIX) and not resolved.startswith("/tmp"):
            logger.warning("guardrail.path_blocked", path=value, resolved=resolved)
            return {
                "continue_": False,
                "decision": "block",
                "reason": f"Guardrail: path outside workspace — {value}",
            }
    return {"continue_": True}


async def post_guardrail(payload: dict) -> dict:
    response = str(payload.get("tool_response", "")).lower()
    for keyword in INVESTMENT_KEYWORDS:
        if keyword in response:
            return {
                "continue_": False,
                "decision": "block",
                "reason": "Guardrail: investment advice detected",
            }
    return {"continue_": True}
