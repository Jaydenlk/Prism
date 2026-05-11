from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_ENABLED = bool(os.environ.get("MEM0_LLM_API_KEY", ""))


def _build_config() -> dict:
    return {
        "llm": {
            "provider": os.environ.get("MEM0_LLM_PROVIDER", "anthropic"),
            "config": {
                "model": os.environ.get("MEM0_LLM_MODEL", "claude-sonnet-4-6"),
                "api_key": os.environ.get("MEM0_LLM_API_KEY", ""),
                "base_url": os.environ.get("MEM0_LLM_BASE_URL", ""),
            },
        },
        "embedder": {
            "provider": os.environ.get("MEM0_EMBEDDER_PROVIDER", "openai"),
            "config": {
                "model": os.environ.get("MEM0_EMBEDDER_MODEL", "text-embedding-3-small"),
                "api_key": os.environ.get("MEM0_EMBEDDER_API_KEY", ""),
            },
        },
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": os.environ.get("POSTGRES_HOST", "postgres"),
                "port": int(os.environ.get("POSTGRES_PORT", "5432")),
                "user": os.environ.get("POSTGRES_USER", "prism"),
                "password": os.environ.get("POSTGRES_PASSWORD", ""),
                "dbname": os.environ.get("POSTGRES_DB", "prism"),
                "embedding_model_dims": 1536,
            },
        },
    }


class MemoryManager:
    def __init__(self) -> None:
        if _ENABLED:
            from mem0 import AsyncMemory
            self._memory: object = AsyncMemory.from_config(_build_config())
        else:
            self._memory = None

    async def recall(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        if self._memory is None:
            return []
        try:
            results = await self._memory.search(query=query, filters={"user_id": user_id}, top_k=limit)  # type: ignore[union-attr]
            return results.get("results", [])
        except Exception as exc:
            logger.warning("memory_recall_error", user_id=user_id, error=str(exc))
            return []

    async def extract_and_store(self, user_id: str, messages: list[dict]) -> list[dict]:
        if self._memory is None or not messages:
            return []
        try:
            result = await self._memory.add(messages=messages, user_id=user_id)  # type: ignore[union-attr]
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.warning("memory_store_error", user_id=user_id, error=str(exc))
            return []

    async def get_all(self, user_id: str) -> list[dict]:
        if self._memory is None:
            return []
        try:
            return await self._memory.get_all(filters={"user_id": user_id})  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("memory_get_all_error", user_id=user_id, error=str(exc))
            return []

    async def delete(self, memory_id: str) -> None:
        if self._memory is None:
            return
        try:
            await self._memory.delete(memory_id=memory_id)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("memory_delete_error", memory_id=memory_id, error=str(exc))

    async def search(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        return await self.recall(user_id, query, limit)

    def build_prompt_section(self, memories: list[dict]) -> str:
        if not memories:
            return ""
        lines = ["## 关于用户", "你已经了解以下信息："]
        for m in memories:
            content = m.get("memory", m.get("text", ""))
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)
