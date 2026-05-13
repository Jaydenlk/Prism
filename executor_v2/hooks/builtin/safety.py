from __future__ import annotations

import hashlib
from collections import deque

import structlog

logger = structlog.get_logger(__name__)

LOOP_WINDOW = 10
LOOP_THRESHOLD = 3
FAILURE_THRESHOLD = 5


class SafetyState:
    def __init__(self) -> None:
        self.recent_calls: deque[str] = deque(maxlen=LOOP_WINDOW)
        self.consecutive_failures: int = 0


_state = SafetyState()


def _call_key(payload: dict) -> str:
    tool_name = payload.get("tool_name", "")
    tool_input = str(sorted(payload.get("tool_input", {}).items()))
    return hashlib.sha256(f"{tool_name}:{tool_input}".encode()).hexdigest()[:16]


async def safety_handler(payload: dict) -> dict:
    if payload.get("_is_failure", False):
        _state.consecutive_failures += 1
        logger.info("safety.failure", count=_state.consecutive_failures)
    else:
        _state.consecutive_failures = 0

    if _state.consecutive_failures >= FAILURE_THRESHOLD:
        logger.warning("safety.circuit_breaker", count=_state.consecutive_failures)
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Safety: circuit breaker — {_state.consecutive_failures} consecutive failures",
        }

    key = _call_key(payload)
    _state.recent_calls.append(key)

    if _state.recent_calls.count(key) >= LOOP_THRESHOLD:
        logger.warning("safety.loop_detected", tool=payload.get("tool_name"))
        return {
            "continue_": False,
            "decision": "block",
            "reason": "Safety: tool call loop detected",
        }

    return {"continue_": True}
