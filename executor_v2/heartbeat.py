from __future__ import annotations

import asyncio
import time

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)


async def run_heartbeat(
    redis_url: str,
    run_id: str,
    stop_event: asyncio.Event,
    interval: int = 5,
    ttl: int = 60,
) -> None:
    key = f"harness:heartbeat:{run_id}"
    client: aioredis.Redis = aioredis.from_url(redis_url)
    try:
        while True:
            try:
                await client.setex(key, ttl, str(int(time.time())))
            except Exception as exc:
                log.warning("heartbeat.write_failed", run_id=run_id, error=str(exc))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
    finally:
        try:
            await client.delete(key)
        except Exception as exc:
            log.warning("heartbeat.delete_failed", run_id=run_id, error=str(exc))
        await client.aclose()
