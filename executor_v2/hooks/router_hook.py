from __future__ import annotations

import structlog

from executor_v2.hooks.registry import (
    HookHandler,
    HookRegistry,
    SESSION_START,
)

logger = structlog.get_logger(__name__)

# Intent → Skill 映射
_SKILL_MAP: dict[str, object] = {}


def _load_skills() -> dict[str, object]:
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
    def __init__(self, prompt: str, user_id: str) -> None:
        self._prompt = prompt
        self._user_id = user_id
        self._router = None
        self.matched_skill = None  # 供外部读取

    def _get_router(self):
        if self._router is None:
            from executor_v2.userbrain.router import IntentRouter
            self._router = IntentRouter()
        return self._router

    async def on_session_start(self, payload: dict) -> dict:
        router = self._get_router()

        # 获取用户记忆做上下文
        memories: list[dict] = []
        try:
            from executor_v2.userbrain.memory import MemoryManager
            mem = MemoryManager()
            memories = await mem.recall(self._user_id, self._prompt)
        except Exception:
            pass

        intent = await router.classify(self._prompt, memories)
        skills = _load_skills()
        skill = skills.get(intent.category, skills["chat"])

        self.matched_skill = skill
        logger.info(
            "router.matched",
            intent=intent.category,
            confidence=intent.confidence,
            skill=getattr(skill, 'name', 'chat'),
        )

        # 将 skill 信息存到 payload 供下游消费
        payload["_skill_name"] = getattr(skill, 'name', '')
        payload["_skill_prompt"] = getattr(skill, 'system_prompt_addition', '')

        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(
            SESSION_START,
            HookHandler(callback=self.on_session_start, priority=3, category="observability"),
        )
