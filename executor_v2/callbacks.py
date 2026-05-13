from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

_RETRY_DELAYS = (0.5, 1.0, 2.0)


class BackendCallback:
    def __init__(
        self,
        callback_url: str,
        callback_secret: str,
        run_id: str,
        session_id: str,
        redis_url: str,
    ) -> None:
        self._callback_url = callback_url
        self._callback_secret = callback_secret
        self._run_id = run_id
        self._session_id = session_id
        self._http = httpx.AsyncClient(
            headers={"X-Callback-Secret": callback_secret},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )
        self._redis = aioredis.from_url(redis_url)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def text_delta(self, text: str, message_id: str) -> None:
        payload = json.dumps(
            {
                "type": "text_delta",
                "run_id": self._run_id,
                "session_id": self._session_id,
                "message_id": message_id,
                "text": text,
                "ts": self._now(),
            }
        )
        try:
            await self._redis.publish(f"run:{self._run_id}:stream", payload)
        except Exception as exc:
            logger.warning("text_delta_publish_failed", error=str(exc))

    async def _http_post(self, event_type: str, data: dict) -> None:
        payload = {
            "run_id": self._run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": self._now(),
        }
        last_exc: Exception | str | None = None
        for attempt, delay in enumerate(_RETRY_DELAYS):
            try:
                resp = await self._http.post(self._callback_url, json=payload)
                if resp.status_code < 500:
                    if resp.status_code >= 400:
                        logger.warning(
                            "callback_4xx",
                            event_type=event_type,
                            status=resp.status_code,
                        )
                    return
                last_exc = f"HTTP {resp.status_code}"
                logger.warning(
                    "callback_5xx",
                    event_type=event_type,
                    status=resp.status_code,
                    attempt=attempt,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "callback_network_error",
                    event_type=event_type,
                    attempt=attempt,
                    error=str(exc),
                )
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

        logger.error("callback_dlq", event_type=event_type, run_id=self._run_id)
        await self._redis.rpush(
            f"callback:dlq:{self._run_id}",
            json.dumps(payload),
        )

    async def tool_start(
        self, tool_use_id: str, tool_name: str, tool_input: dict
    ) -> None:
        await self._http_post(
            "tool_start",
            {"tool_use_id": tool_use_id, "tool_name": tool_name, "tool_input": tool_input},
        )

    async def tool_end(
        self,
        tool_use_id: str,
        tool_name: str,
        output: str,
        is_error: bool,
        duration_ms: int,
    ) -> None:
        await self._http_post(
            "tool_end",
            {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "output": output,
                "is_error": is_error,
                "duration_ms": duration_ms,
            },
        )

    async def message_complete(
        self,
        role: str,
        content: list,
        sequence_no_hint: int | None = None,
    ) -> None:
        data: dict = {"role": role, "content": content}
        if sequence_no_hint is not None:
            data["sequence_no_hint"] = sequence_no_hint
        await self._http_post("message_complete", data)

    async def run_complete(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cache_creation_tokens: int = 0,
        turn_count: int = 0,
    ) -> None:
        await self._http_post(
            "run_complete",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_hit_tokens": cache_hit_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "turn_count": turn_count,
            },
        )

    async def run_error(self, error: str) -> None:
        await self._http_post("run_error", {"error": error})

    async def close(self) -> None:
        await self._http.aclose()
        await self._redis.aclose()
