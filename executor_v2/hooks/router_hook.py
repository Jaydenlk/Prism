from __future__ import annotations

import structlog

from executor_v2.hooks.registry import (
    HookHandler,
    HookRegistry,
    SESSION_START,
)

logger = structlog.get_logger(__name__)

_SKILL_MAP: dict[str, object] = {}


def load_skills() -> dict[str, object]:
    if _SKILL_MAP:
        return _SKILL_MAP
    from executor_v2.skills.chat import CHAT_SKILL
    from executor_v2.skills.memo import MEMO_SKILL
    from executor_v2.skills.reminder import REMINDER_SKILL
    from executor_v2.skills.research import RESEARCH_SKILL
    from executor_v2.skills.brainstorm import BRAINSTORM_SKILL
    from executor_v2.skills.writing import WRITING_SKILL
    from executor_v2.skills.analysis import ANALYSIS_SKILL
    from executor_v2.skills.meeting import MEETING_SKILL
    _SKILL_MAP.update({
        "chat": CHAT_SKILL,
        "memo": MEMO_SKILL,
        "reminder": REMINDER_SKILL,
        "research": RESEARCH_SKILL,
        "brainstorm": BRAINSTORM_SKILL,
        "writing": WRITING_SKILL,
        "analysis": ANALYSIS_SKILL,
        "meeting": MEETING_SKILL,
    })
    return _SKILL_MAP


class RouterHook:
    """Logs session start with skill info injected by __main__.py.

    Intent classification and skill selection happen eagerly in __main__.py
    before the runtime starts (because skill_prompt must be in the system
    prompt at SDK connect time). This hook only records the event.
    """

    def __init__(self, prompt: str, user_id: str) -> None:
        self._prompt = prompt
        self._user_id = user_id

    async def on_session_start(self, payload: dict) -> dict:
        logger.info(
            "router.session_start",
            skill=payload.get("_skill_name", ""),
            user_id=self._user_id,
        )
        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(
            SESSION_START,
            HookHandler(callback=self.on_session_start, priority=3, category="observability"),
        )
