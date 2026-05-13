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
    def __init__(self, prompt: str, user_id: str, mem: object | None = None) -> None:
        self._prompt = prompt
        self._user_id = user_id
        self._mem = mem
        self.matched_skill: object | None = None

    async def on_session_start(self, payload: dict) -> dict:
        from executor_v2.userbrain.router import IntentRouter

        memories: list[dict] = []
        if self._mem is not None:
            try:
                memories = await self._mem.recall(self._user_id, self._prompt)
            except Exception:
                pass

        intent = await IntentRouter().classify(self._prompt, memories)
        skills = load_skills()
        skill = skills.get(intent.category, skills["chat"])
        self.matched_skill = skill

        logger.info(
            "router.matched",
            intent=intent.category,
            confidence=intent.confidence,
            skill=getattr(skill, "name", "chat"),
        )

        payload["_skill_name"] = getattr(skill, "name", "")
        payload["_skill_prompt"] = getattr(skill, "system_prompt_addition", "")

        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(
            SESSION_START,
            HookHandler(callback=self.on_session_start, priority=3, category="observability"),
        )
