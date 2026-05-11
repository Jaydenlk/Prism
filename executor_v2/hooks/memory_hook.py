from __future__ import annotations

import structlog

from executor_v2.config import RunConfig
from executor_v2.hooks.registry import (
    HookHandler,
    HookRegistry,
    MESSAGE_COMPLETE,
    SESSION_END,
    SESSION_START,
)
from executor_v2.userbrain.memory import MemoryManager

logger = structlog.get_logger(__name__)


class MemoryHook:
    def __init__(self, memory_manager: MemoryManager, config: RunConfig) -> None:
        self._memory = memory_manager
        self._config = config
        self._conversation_messages: list[dict] = []

    async def on_session_start(self, payload: dict) -> dict:
        memories = await self._memory.recall(self._config.user_id, self._config.prompt)
        if memories:
            section = self._memory.build_prompt_section(memories)
            logger.info("memory_injected", user_id=self._config.user_id, count=len(memories))
            self._config.system_prompt = (
                f"{self._config.system_prompt}\n\n{section}".strip()
                if self._config.system_prompt
                else section
            )
        return {"continue_": True}

    async def on_message_complete(self, payload: dict) -> dict:
        role = payload.get("role", "")
        blocks = payload.get("blocks", [])
        text_parts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text")]
        if role and text_parts:
            self._conversation_messages.append({"role": role, "content": " ".join(text_parts)})
        return {"continue_": True}

    async def on_session_end(self, payload: dict) -> dict:
        if self._conversation_messages:
            await self._memory.extract_and_store(self._config.user_id, self._conversation_messages)
            logger.info("memory_extracted", user_id=self._config.user_id, turns=len(self._conversation_messages))
        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(SESSION_START, HookHandler(callback=self.on_session_start, priority=5, category="observability"))
        registry.register(MESSAGE_COMPLETE, HookHandler(callback=self.on_message_complete, priority=5, category="observability"))
        registry.register(SESSION_END, HookHandler(callback=self.on_session_end, priority=5, category="observability"))
