from __future__ import annotations

import structlog

from executor_v2.hooks.registry import (
    HookHandler,
    HookRegistry,
    MESSAGE_COMPLETE,
)

logger = structlog.get_logger(__name__)


class VerifyHook:
    def __init__(self, prompt: str, user_id: str, mem: object | None = None) -> None:
        self._prompt = prompt
        self._user_id = user_id
        self._verify_agent = None
        self._mem = mem
        self._cached_memories: list[dict] | None = None

    def _get_verify_agent(self):
        if self._verify_agent is None:
            from executor_v2.userbrain.verify import VerifyAgent
            self._verify_agent = VerifyAgent()
        return self._verify_agent

    async def on_message_complete(self, payload: dict) -> dict:
        role = payload.get("role", "")
        blocks = payload.get("blocks", [])

        if role != "assistant":
            return {"continue_": True}

        text_parts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text")]
        if not text_parts:
            return {"continue_": True}

        result_text = " ".join(text_parts)

        from executor_v2.userbrain.verify import should_verify
        if not should_verify(self._prompt):
            return {"continue_": True}

        verify_agent = self._get_verify_agent()

        if self._cached_memories is None:
            self._cached_memories = []
            if self._mem is not None:
                try:
                    self._cached_memories = await self._mem.recall(self._user_id, self._prompt)
                except Exception:
                    pass
        verify_result = await verify_agent.verify(
            task=self._prompt,
            result=result_text,
            user_memories=self._cached_memories,
        )

        logger.info(
            "verify.result",
            confidence=verify_result.confidence.value,
            completeness=verify_result.completeness_score,
            consistency=verify_result.consistency_score,
            uncertain_claims=len(verify_result.uncertain_claims),
        )

        payload["_confidence"] = verify_result.confidence.value
        payload["_uncertain_claims"] = verify_result.uncertain_claims

        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(
            MESSAGE_COMPLETE,
            HookHandler(callback=self.on_message_complete, priority=10, category="observability"),
        )
