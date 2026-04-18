"""
Permission Ask 反向通信协议（v4 新增，ADR-028）

子进程通过 Redis BLPOP 阻塞等待用户回答。
Backend 通过 SSE 把 permission_ask 事件推给前端。
用户点击后 Backend POST /sessions/{id}/permission-answer，RPUSH 到 Redis。
子进程 BLPOP 返回 → 继续执行。

超时（默认 300s）默认 deny（fail-safe）。

Redis key 命名（严格对齐 DOC-07 Task 7.3）：
- 请求写入：perm_req:{request_id}    SETEX TTL=timeout_seconds
- 应答等待：perm_answer:{request_id}  BLPOP

uuid7 fallback 到 uuid4（若 uuid_extensions 未安装）。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal

import redis.asyncio as redis_async
import structlog

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()

PERMISSION_ASK_TIMEOUT_SECONDS = int(
    os.environ.get("PERMISSION_ASK_TIMEOUT_SECONDS", "300")
)


def _new_request_id() -> str:
    """生成请求 ID：优先 uuid7，fallback uuid4"""
    try:
        from uuid_extensions import uuid7
        return str(uuid7())
    except Exception:
        import uuid
        return str(uuid.uuid4())


class PermissionAskProtocol:
    """Redis BLPOP 反向通信协议（ADR-028）"""

    def __init__(self, redis_url: str, callback: "BackendCallback"):
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._callback = callback

    async def ask(
        self,
        run_id: str,
        tool_name: str,
        tool_input: dict,
        reason: str,
        timeout_seconds: int = PERMISSION_ASK_TIMEOUT_SECONDS,
    ) -> Literal["allow", "deny"]:
        """
        发起 permission ask 请求，阻塞等待用户回答。
        返回 'allow' 或 'deny'。超时默认 deny（fail-safe）。

        Redis keys：
        - perm_req:{request_id}    — 存请求详情，TTL=timeout_seconds
        - perm_answer:{request_id} — BLPOP 阻塞等待（Backend 端 RPUSH）
        """
        request_id = _new_request_id()
        answer_key = f"perm_answer:{request_id}"
        req_key = f"perm_req:{request_id}"
        timeout_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

        # 写入请求详情到 Redis（供 Backend 查询/回查）
        await self._redis.setex(
            req_key,
            timeout_seconds,
            json.dumps({
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": reason,
                "timeout_at": timeout_at.isoformat(),
            }),
        )

        # 通过 HTTP 回调推送 permission_ask 事件（Backend → SSE → 前端弹窗）
        await self._callback.permission_ask(
            request_id=request_id,
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
            timeout_at=timeout_at.isoformat(),
        )

        logger.info(
            "harness.permission_ask.pending",
            request_id=request_id,
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
        )

        # BLPOP 阻塞等待用户回答（陷阱 #8：必须 BLPOP，不能轮询）
        # timeout=0 会永久阻塞，必须传 timeout_seconds
        result = await self._redis.blpop(answer_key, timeout=timeout_seconds)

        if result is None:
            # 超时 → fail-safe deny
            logger.warning(
                "harness.permission_ask.timeout",
                request_id=request_id,
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
            )
            await self._callback.harness_event("permission_ask_timeout", {
                "request_id": request_id,
                "tool_name": tool_name,
            })
            return "deny"

        _, answer = result
        if answer not in ("allow", "deny"):
            logger.error(
                "harness.permission_ask.invalid_answer",
                request_id=request_id,
                answer=answer,
            )
            return "deny"

        logger.info(
            "harness.permission_ask.answered",
            request_id=request_id,
            tool_name=tool_name,
            decision=answer,
        )
        return answer  # type: ignore[return-value]

    async def close(self) -> None:
        """释放 Redis 连接"""
        await self._redis.aclose()
