"""
Prism v2 — SSE Manager (DOC-07 Task 7.3, ADR-063)

Redis pub/sub 推送层：
  - publish()          : 写 sse:{session_id} pub/sub + sse:{session_id}:stream Stream
  - subscribe()        : 返回 PubSub 对象供 SSE 端点 listen
  - backfill_since()   : 从 Redis Stream 补发 last_event_id 之后的事件
  - acquire_conn_slot(): 多 tab 限制，每 session 最多 3 个 SSE 连接
  - release_conn_slot(): 断开连接时释放槽位

Channel 约定：
  sse:{session_id}        — pub/sub，实时转发
  sse:{session_id}:stream — Redis Stream，最近 200 条用于断线重连补发
  sse:conns:{session_id}  — Counter，tab 限制（ADR-063）

同时作为 Redis 直通 forwarder 的 target：
  子进程向 run:{run_id}:stream 发布，callback_service 读取后
  调用 publish() 转到 sse:{session_id}，统一 SSE 格式。
"""
from __future__ import annotations

import json
from typing import Any

import redis as redis_lib
import redis.asyncio as aioredis

import structlog
logger = structlog.get_logger()


class SSEManager:
    """
    v4 SSE 推送管理器（ADR-063）。

    同时支持：
      1. 关键事件（callback_service 主动 publish）
      2. Redis 直通 forward（callback_service 将 run:{run_id}:stream 的 delta 桥接过来）
    """

    MAX_CONNS_PER_SESSION: int = 3
    STREAM_BUFFER_SIZE: int = 200  # 最近 200 条用于 last_event_id 补发

    def __init__(self, redis_url: str) -> None:
        # 同步客户端（用于 subscribe/blocking 场景）
        self._redis_sync = redis_lib.from_url(redis_url, decode_responses=False)
        # 异步客户端（用于 publish/backfill/slot 管理）
        self._redis_async: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=False
        )

    # ------------------------------------------------------------------
    # Publish（异步）
    # ------------------------------------------------------------------

    async def publish(
        self,
        session_id: str,
        event_name: str,
        data: dict[str, Any],
        event_id: str | None = None,
    ) -> None:
        """
        发布 SSE 事件。

        1. 实时 pub/sub → 在线连接立即收到
        2. 写入 Redis Stream → 供断线重连 backfill
        """
        try:
            from uuid_extensions import uuid7
            eid = event_id or str(uuid7())
        except ImportError:
            import uuid
            eid = event_id or str(uuid.uuid4())

        payload = {"id": eid, "event": event_name, "data": data}
        serialized = json.dumps(payload)

        # 1. pub/sub 实时推送
        await self._redis_async.publish(f"sse:{session_id}", serialized)

        # 2. Redis Stream 写入（用于 last_event_id 补发）
        await self._redis_async.xadd(
            f"sse:{session_id}:stream",
            {"payload": serialized},
            maxlen=self.STREAM_BUFFER_SIZE,
            approximate=True,
        )

    # ------------------------------------------------------------------
    # Subscribe（同步，供同步 generator 使用）
    # ------------------------------------------------------------------

    def subscribe(self, session_id: str) -> redis_lib.client.PubSub:
        """
        订阅 Redis pub/sub channel，返回 PubSub 对象。

        调用方在生成器中 for message in pubsub.listen() 即可。
        子进程直通 channel（run:{run_id}:stream）由 callback_service
        通过 publish() 桥接到此 channel，无需额外订阅。
        """
        pubsub = self._redis_sync.pubsub()
        pubsub.subscribe(f"sse:{session_id}")
        return pubsub

    # ------------------------------------------------------------------
    # Backfill（异步，供 SSE 端点补发历史）
    # ------------------------------------------------------------------

    async def backfill_since(
        self, session_id: str, last_event_id: str
    ) -> list[dict[str, Any]]:
        """
        从 Redis Stream 补发 last_event_id 之后的事件。

        遍历 sse:{session_id}:stream，跳过 last_event_id 之前（含）的事件，
        返回之后的所有事件列表（保持顺序）。
        如果 last_event_id 不在 Stream 中（可能已被 maxlen 裁剪），
        返回全部缓存（最多 STREAM_BUFFER_SIZE 条）。
        """
        entries = await self._redis_async.xrange(
            f"sse:{session_id}:stream",
            min="-",
            max="+",
        )
        result: list[dict] = []
        found = False
        for _entry_id, fields in entries:
            raw_payload = fields.get(b"payload") or fields.get("payload")
            if raw_payload is None:
                continue
            payload: dict = json.loads(raw_payload)
            if found:
                result.append(payload)
            elif payload.get("id") == last_event_id:
                found = True

        # last_event_id 在缓存中不存在 → 补发所有缓存
        if not found and entries:
            result = [
                json.loads(
                    (f.get(b"payload") or f.get("payload", b"{}"))
                )
                for _, f in entries
            ]

        return result

    # ------------------------------------------------------------------
    # Connection slot management（多 tab 限制）
    # ------------------------------------------------------------------

    async def acquire_conn_slot(self, session_id: str) -> bool:
        """
        尝试占用 SSE 连接槽位。

        每 session 最多 MAX_CONNS_PER_SESSION(3) 个并发 SSE 连接。
        页面刷新时旧连接可能未及时释放导致计数器虚高，
        超限时检查 TTL——若 key 已存在较久（>60s），重置计数器并放行。
        """
        key = f"sse:conns:{session_id}"
        count: int = await self._redis_async.incr(key)
        if count == 1:
            await self._redis_async.expire(key, 3600)
        if count > self.MAX_CONNS_PER_SESSION:
            await self._redis_async.decr(key)
            ttl = await self._redis_async.ttl(key)
            if ttl > 60:
                await self._redis_async.set(key, 1, ex=3600)
                return True
            return False
        return True

    async def release_conn_slot(self, session_id: str) -> None:
        """释放 SSE 连接槽位（连接断开时调用）。"""
        key = f"sse:conns:{session_id}"
        current = await self._redis_async.decr(key)
        # 防止负值
        if current < 0:
            await self._redis_async.set(key, 0)

    # ------------------------------------------------------------------
    # Async subscribe（供 async generator 使用）
    # ------------------------------------------------------------------

    def subscribe_async(self, session_id: str) -> aioredis.client.PubSub:
        """
        返回异步 PubSub 对象（供 async for message in pubsub.listen() 使用）。
        """
        pubsub = self._redis_async.pubsub()
        return pubsub

    async def start_subscribe_async(self, session_id: str) -> aioredis.client.PubSub:
        """订阅并返回 async PubSub 对象。"""
        pubsub = self._redis_async.pubsub()
        await pubsub.subscribe(f"sse:{session_id}")
        return pubsub
