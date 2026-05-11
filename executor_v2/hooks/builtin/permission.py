from __future__ import annotations

DANGEROUS_TOOLS: set[str] = set()


async def permission_handler(payload: dict) -> dict:
    tool_name = payload.get("tool_name", "")
    if tool_name in DANGEROUS_TOOLS:
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Tool '{tool_name}' blocked by permission policy",
        }
    return {"continue_": True}
