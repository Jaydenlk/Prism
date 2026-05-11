from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


async def observability_handler(payload: dict) -> dict:
    logger.info(
        "hook.event",
        event=payload.get("_event", "unknown"),
        tool_name=payload.get("tool_name"),
    )
    return {"continue_": True}
