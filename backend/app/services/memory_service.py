from __future__ import annotations

import os

import structlog
from fastapi import HTTPException, status

logger = structlog.get_logger()

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_ENABLED = bool(_API_KEY)


def _build_config() -> dict:
    config: dict = {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": os.environ.get("MEM0_MODEL", "claude-haiku-4-5-20251001"),
                "api_key": _API_KEY,
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
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if base_url:
        config["llm"]["config"]["base_url"] = base_url
    return config


_memory_instance: object | None = None


def _get_memory() -> object:
    global _memory_instance
    if _memory_instance is None:
        from mem0 import AsyncMemory
        _memory_instance = AsyncMemory.from_config(_build_config())
    return _memory_instance


class MemoryService:
    def __init__(self) -> None:
        pass

    def _require_enabled(self) -> None:
        if not _ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service not configured (ANTHROPIC_API_KEY missing)",
            )

    async def list_memories(self, user_id: str) -> list[dict]:
        self._require_enabled()
        mem = _get_memory()
        try:
            result = await mem.get_all(filters={"user_id": user_id})
            return result if isinstance(result, list) else []
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.list_error", error=str(exc))
            return []

    async def add_memory(self, user_id: str, content: str) -> dict:
        self._require_enabled()
        mem = _get_memory()
        try:
            result = await mem.add(
                messages=[{"role": "user", "content": content}],
                user_id=user_id,
            )
            return {"status": "ok", "result": result}
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("memory.add_error", error=str(exc))
            raise HTTPException(status_code=502, detail="Memory add failed")

    async def delete_memory(self, user_id: str, memory_id: str) -> None:
        self._require_enabled()
        mem = _get_memory()
        try:
            all_memories = await mem.get_all(filters={"user_id": user_id})
            owned_ids = set()
            if isinstance(all_memories, list):
                owned_ids = {m.get("id") for m in all_memories}
            elif isinstance(all_memories, dict):
                owned_ids = {m.get("id") for m in all_memories.get("results", [])}
            if memory_id not in owned_ids:
                raise HTTPException(status_code=404, detail="Memory not found")
            await mem.delete(memory_id=memory_id)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("memory.delete_error", error=str(exc))
            raise HTTPException(status_code=502, detail="Memory delete failed")

    async def search_memories(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        self._require_enabled()
        mem = _get_memory()
        try:
            results = await mem.search(query=query, filters={"user_id": user_id}, top_k=limit)
            return results.get("results", []) if isinstance(results, dict) else []
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("memory.search_error", error=str(exc))
            return []
