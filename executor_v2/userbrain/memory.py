from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)


class MemoryManager:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "")
        self._model = model or os.environ.get("MEM0_MODEL", "auto-v2")
        self._memory: object | None = None

        if self._api_key:
            self._init_mem0()

    def _init_mem0(self) -> None:
        try:
            from mem0 import AsyncMemory

            config: dict = {
                "llm": {
                    "provider": "anthropic",
                    "config": {
                        "model": self._model or "claude-haiku-4-5-20251001",
                        "api_key": self._api_key,
                    },
                },
                "embedder": {
                    "provider": "huggingface",
                    "config": {
                        "model": "sentence-transformers/all-MiniLM-L6-v2",
                        "model_kwargs": {"device": "cpu"},
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
                        "embedding_model_dims": 384,
                    },
                },
            }

            if self._base_url:
                os.environ.setdefault("ANTHROPIC_BASE_URL", self._base_url)

            self._memory = AsyncMemory.from_config(config)
            logger.info("memory.initialized", model=self._model)
        except Exception as exc:
            logger.warning("memory.init_failed", error=str(exc))
            self._memory = None

    async def recall(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        if self._memory is None:
            return []
        try:
            results = await self._memory.search(query=query, filters={"user_id": user_id}, top_k=limit)
            return results.get("results", []) if isinstance(results, dict) else []
        except Exception as exc:
            logger.warning("memory.recall_error", error=str(exc))
            return []

    async def extract_and_store(self, user_id: str, messages: list[dict]) -> list[dict]:
        if self._memory is None or not messages:
            return []
        try:
            result = await self._memory.add(messages=messages, user_id=user_id)
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.warning("memory.store_error", error=str(exc))
            return []

    async def get_all(self, user_id: str) -> list[dict]:
        if self._memory is None:
            return []
        try:
            result = await self._memory.get_all(filters={"user_id": user_id})
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.warning("memory.get_all_error", error=str(exc))
            return []

    async def delete(self, memory_id: str) -> None:
        if self._memory is None:
            return
        try:
            await self._memory.delete(memory_id=memory_id)
        except Exception as exc:
            logger.warning("memory.delete_error", error=str(exc))

    def build_prompt_section(self, memories: list[dict]) -> str:
        if not memories:
            return ""
        lines = ["## 关于用户", "你已经了解以下信息："]
        for m in memories:
            content = m.get("memory", m.get("text", ""))
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)
