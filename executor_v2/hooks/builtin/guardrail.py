from __future__ import annotations

import os

INVESTMENT_KEYWORDS: set[str] = {
    "投资",
    "理财",
    "炒股",
    "基金推荐",
    "股票推荐",
    "buy stock",
    "investment advice",
}

_ALLOWED_PATHS_PREFIX = os.path.expanduser("~")


async def guardrail_handler(payload: dict) -> dict:
    response = str(payload.get("tool_response", ""))
    for keyword in INVESTMENT_KEYWORDS:
        if keyword in response.lower():
            return {
                "continue_": False,
                "decision": "block",
                "reason": "Guardrail: investment advice detected",
            }

    tool_input = payload.get("tool_input") or {}
    for value in tool_input.values():
        path = str(value)
        if path.startswith("/") or path.startswith("\\"):
            resolved = os.path.realpath(path)
            if not resolved.startswith(_ALLOWED_PATHS_PREFIX):
                return {
                    "continue_": False,
                    "decision": "block",
                    "reason": f"Guardrail: path access denied — {path}",
                }

    return {"continue_": True}
