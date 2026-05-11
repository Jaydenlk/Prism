from __future__ import annotations

import os

import structlog
from fastapi import HTTPException, status

logger = structlog.get_logger()

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


class MemoryService:
    def __init__(self) -> None:
        if _ENABLED:
            from mem0 import AsyncMemory
            self._memory: object = AsyncMemory.from_config(_build_config())
        else:
            self._memory = None

    def _require_enabled(self) -> None:
        if self._memory is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service is not configured (MEM0_LLM_API_KEY missing)",
            )

    async def list_memories(self, user_id: str) -> list[dict]:
        self._require_enabled()
        try:
            result = await self._memory.get_all(filters={"user_id": user_id})  # type: ignore[union-attr]
            return result if isinstance(result, list) else []
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.list_error", user_id=user_id, error=str(exc))
            return []

    async def add_memory(self, user_id: str, content: str) -> dict:
        self._require_enabled()
        try:
            result = await self._memory.add(  # type: ignore[union-attr]
                messages=[{"role": "user", "content": content}],
                user_id=user_id,
            )
            return result if isinstance(result, dict) else {"result": result}
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.add_error", user_id=user_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to add memory",
            )

    async def delete_memory(self, memory_id: str) -> None:
        self._require_enabled()
        try:
            await self._memory.delete(memory_id=memory_id)  # type: ignore[union-attr]
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.delete_error", memory_id=memory_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete memory",
            )

    async def search_memories(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        self._require_enabled()
        try:
            results = await self._memory.search(  # type: ignore[union-attr]
                query=query,
                filters={"user_id": user_id},
                top_k=limit,
            )
            return results.get("results", []) if isinstance(results, dict) else []
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.search_error", user_id=user_id, error=str(exc))
            return []
