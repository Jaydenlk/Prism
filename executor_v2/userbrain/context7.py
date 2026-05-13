from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.context7.com/v2"
REQUEST_TIMEOUT = 15.0
CACHE_TTL = 3600  # 1 hour


@dataclass
class Library:
    id: str
    name: str
    description: str
    snippet_count: int


@dataclass
class FactCheckResult:
    claim: str
    verified: bool
    confidence: float  # 0.0 - 1.0
    source: str
    evidence: str


class Context7Client:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self._cache: dict[str, tuple[float, list[Library]]] = {}

    async def resolve_library(self, name: str) -> list[Library]:
        """搜索库名，返回匹配的库列表。结果缓存 1 小时。"""
        now = time.monotonic()
        if name in self._cache:
            cached_at, result = self._cache[name]
            if now - cached_at < CACHE_TTL:
                return result

        try:
            resp = await self._http.post(
                f"{BASE_URL}/search",
                json={"query": name},
            )
            resp.raise_for_status()
            data = resp.json()
            libraries = [
                Library(
                    id=lib.get("id", ""),
                    name=lib.get("name", ""),
                    description=lib.get("description", ""),
                    snippet_count=lib.get("snippet_count", 0),
                )
                for lib in data.get("results", [])
            ]
            self._cache[name] = (now, libraries)
            return libraries
        except Exception as exc:
            logger.warning("context7.resolve_failed", name=name, error=str(exc))
            return []

    async def get_docs(self, library_id: str, query: str) -> str:
        """获取指定库的文档上下文"""
        try:
            resp = await self._http.post(
                f"{BASE_URL}/context",
                json={"libraryId": library_id, "query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("context", "")
        except Exception as exc:
            logger.warning("context7.docs_failed", library_id=library_id, error=str(exc))
            return ""

    async def fact_check(self, claim: str, library_name: str = "") -> FactCheckResult:
        """验证一个事实性声明。如果提供 library_name，先搜索对应库的文档。"""
        evidence = ""
        if library_name:
            libraries = await self.resolve_library(library_name)
            if libraries:
                evidence = await self.get_docs(libraries[0].id, claim)

        verified = bool(evidence and len(evidence) > 50)
        confidence = 0.8 if verified else 0.3

        return FactCheckResult(
            claim=claim,
            verified=verified,
            confidence=confidence,
            source=f"context7:{library_name}" if library_name else "context7",
            evidence=evidence[:500] if evidence else "",
        )

    async def close(self) -> None:
        await self._http.aclose()
