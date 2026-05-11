from __future__ import annotations

import hashlib

LOOP_WINDOW = 10
LOOP_THRESHOLD = 3
FAILURE_THRESHOLD = 5


class SafetyState:
    def __init__(self) -> None:
        self.recent_calls: list[str] = []
        self.consecutive_failures: int = 0


_state = SafetyState()


def _call_key(payload: dict) -> str:
    tool_name = payload.get("tool_name", "")
    tool_input = str(payload.get("tool_input", ""))
    return hashlib.md5(f"{tool_name}:{tool_input}".encode()).hexdigest()


async def safety_handler(payload: dict) -> dict:
    is_failure = payload.get("_is_failure", False)

    if is_failure:
        _state.consecutive_failures += 1
    else:
        _state.consecutive_failures = 0

    if _state.consecutive_failures >= FAILURE_THRESHOLD:
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Safety: circuit breaker tripped after {_state.consecutive_failures} consecutive failures",
        }

    key = _call_key(payload)
    _state.recent_calls.append(key)
    if len(_state.recent_calls) > LOOP_WINDOW:
        _state.recent_calls.pop(0)

    if _state.recent_calls.count(key) >= LOOP_THRESHOLD:
        return {
            "continue_": False,
            "decision": "block",
            "reason": "Safety: tool call loop detected",
        }

    return {"continue_": True}
