from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

INTENT_CATEGORIES = [
    "memo", "reminder", "research", "brainstorm",
    "writing", "analysis", "meeting", "chat",
]

@dataclass
class Intent:
    category: str
    confidence: float

class IntentRouter:
    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self._model = os.environ.get("ROUTER_MODEL", "claude-haiku-4-5-20251001")
        self._enabled = bool(self._api_key)

    async def classify(self, message: str, user_memories: list[dict] | None = None) -> Intent:
        if not self._enabled or len(message.strip()) < 5:
            return Intent(category="chat", confidence=1.0)

        memory_hint = ""
        if user_memories:
            facts = [m.get("memory", "") for m in user_memories[:5] if m.get("memory")]
            if facts:
                memory_hint = f"\nUser context: {'; '.join(facts)}"

        prompt = (
            f"Classify this message into exactly ONE category: {', '.join(INTENT_CATEGORIES)}\n"
            f"Message: {message[:500]}{memory_hint}\n"
            f"Reply with ONLY the category name, nothing else."
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 20,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content", [])
                if content and content[0].get("type") == "text":
                    category = content[0]["text"].strip().lower()
                    if category in INTENT_CATEGORIES:
                        return Intent(category=category, confidence=0.9)
        except Exception as exc:
            logger.warning("router.classify_failed", error=str(exc))

        return Intent(category="chat", confidence=0.5)
