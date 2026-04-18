"""
Backend 回调客户端（v4 双通道）

方案 A（ADR-022）：
- 高频事件（text_delta, tool_use_delta）→ Redis PUBLISH 直通，Backend SSE Manager
  订阅 channel 立即 forward 给前端。不走 HTTP，避免每 token 穿越 Backend 路由层。
- 关键事件（tool_start/tool_end/message_complete/run_complete/run_error/permission_ask/
  harness_event/coordinator_plan_update）→ HTTP POST 到 Backend 内部接口，带 3 次
  指数退避重试；全部重试失败后入 Redis dead letter queue `callback:dlq:{run_id}`。

Channel 命名：
- 流式直通：`run:{run_id}:stream`
- DLQ：`callback:dlq:{run_id}`

HTTP 请求携带 X-Callback-Secret 头（CALLBACK_SECRET，独立于 JWT_SECRET 和
ENCRYPTION_KEY，启动时 main.py 校验三者不同）。

协议定义：DOC-01 v4 §9.1（回调协议）+ §9.2（Redis namespace 规范）

进程边界：本模块只 import executor.*（以及第三方库），禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis_async
import structlog

logger = structlog.get_logger()

HTTP_MAX_RETRIES = 3
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_BACKOFF_BASE = 0.5  # 退避序列：0.5s, 1.0s, 2.0s


class BackendCallback:
    """Backend 回调客户端（v4 双通道：Redis 高频直通 + HTTP 关键事件重试）"""

    def __init__(
        self,
        callback_url: str,
        callback_secret: str,
        run_id: str,
        session_id: str,
        redis_url: str,
    ) -> None:
        self._url = callback_url
        self._secret = callback_secret
        self._run_id = run_id
        self._session_id = session_id
        self._client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._stream_channel = f"run:{run_id}:stream"

    # -------- 高频路径（Redis 直通，ADR-022）--------

    async def text_delta(self, text: str, message_id: str) -> None:
        """高频事件：走 Redis PUBLISH，Backend SSE 订阅立即 forward"""
        await self._redis.publish(
            self._stream_channel,
            json.dumps(
                {
                    "type": "text_delta",
                    "run_id": self._run_id,
                    "session_id": self._session_id,
                    "message_id": message_id,
                    "text": text,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )

    async def tool_use_delta(self, tool_use_id: str, partial_json: str) -> None:
        """高频事件：工具入参 JSON 流式增量"""
        await self._redis.publish(
            self._stream_channel,
            json.dumps(
                {
                    "type": "tool_use_delta",
                    "run_id": self._run_id,
                    "session_id": self._session_id,
                    "tool_use_id": tool_use_id,
                    "partial_json": partial_json,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )

    # -------- 关键事件（HTTP 带重试，3 次指数退避）--------

    async def _http_post_with_retry(self, event_type: str, data: dict) -> None:
        """POST 到 Backend，3 次指数退避（0.5s / 1.0s / 2.0s）；全失败入 DLQ。

        4xx 客户端错误：只 log，不重试（语义错误，重试无意义）。
        5xx 服务端错误 + 网络异常：重试。
        全部失败：RPUSH 到 `callback:dlq:{run_id}`。
        """
        payload = {
            "run_id": self._run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for attempt in range(HTTP_MAX_RETRIES):
            try:
                resp = await self._client.post(
                    self._url,
                    json=payload,
                    headers={"X-Callback-Secret": self._secret},
                )
                if resp.status_code < 500:
                    # 成功（2xx/3xx）或客户端错误（4xx）— 不重试
                    if resp.status_code >= 400:
                        logger.warning(
                            "harness.callback.client_error",
                            event_type=event_type,
                            status=resp.status_code,
                            body=resp.text[:500],
                        )
                    return
                # 5xx：记录并准备重试
                logger.warning(
                    "harness.callback.server_error",
                    event_type=event_type,
                    status=resp.status_code,
                    attempt=attempt + 1,
                )
            except Exception as e:
                logger.warning(
                    "harness.callback.exception",
                    event_type=event_type,
                    error=str(e),
                    attempt=attempt + 1,
                )

            # 指数退避：0.5s, 1.0s, 2.0s
            await asyncio.sleep(HTTP_BACKOFF_BASE * (2**attempt))

        # 全部失败 → dead letter queue
        logger.error(
            "harness.callback.dlq",
            event_type=event_type,
            run_id=self._run_id,
        )
        try:
            from executor.observability.metrics import prism_callback_dlq_total

            prism_callback_dlq_total.labels(event_type=event_type).inc()
        except Exception:
            pass  # metrics 降级不影响主路径
        await self._redis.rpush(
            f"callback:dlq:{self._run_id}",
            json.dumps(payload),
        )

    async def message_complete(
        self,
        role: str,
        content: list,
        sequence_no_hint: int | None = None,
    ) -> None:
        """消息完整体上报（供 Backend 持久化 messages 表）。

        sequence_no 最终由 Backend DB 层分配（ADR-060 per-session advisory_xact_lock），
        本字段仅作 hint，Backend 可忽略。
        """
        await self._http_post_with_retry(
            "message_complete",
            {
                "role": role,
                "content": content,
                "sequence_no_hint": sequence_no_hint,
            },
        )

    async def tool_start(
        self, tool_use_id: str, tool_name: str, tool_input: dict
    ) -> None:
        """工具开始执行事件（HTTP 带重试）"""
        await self._http_post_with_retry(
            "tool_start",
            {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "input": tool_input,
            },
        )

    async def tool_end(
        self,
        tool_use_id: str,
        output: str,
        is_error: bool,
        duration_ms: int,
    ) -> None:
        """工具执行结束事件（HTTP 带重试）"""
        await self._http_post_with_retry(
            "tool_end",
            {
                "tool_use_id": tool_use_id,
                "output": output[:500],  # 回调 preview，完整内容走 messages 表
                "is_error": is_error,
                "duration_ms": duration_ms,
            },
        )

    async def harness_event(self, event_subtype: str, detail: dict) -> None:
        """Harness 内部事件（compaction / loop_detect / 等）"""
        await self._http_post_with_retry(
            "harness_event",
            {
                "type": event_subtype,
                "detail": detail,
            },
        )

    async def permission_ask(
        self,
        request_id: str,
        tool_name: str,
        tool_input: dict,
        reason: str,
        timeout_at: str,
    ) -> None:
        """权限询问事件（HTTP 带重试；用户应答通过 Redis BLPOP `perm_answer:{request_id}` 回传，Task 3.3）"""
        await self._http_post_with_retry(
            "permission_ask",
            {
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": reason,
                "timeout_at": timeout_at,
            },
        )

    async def compaction_in_progress(
        self, tier: int, before_tokens: int, after_tokens: int
    ) -> None:
        """Compaction 进度事件"""
        await self._http_post_with_retry(
            "harness_event",
            {
                "type": "compaction",
                "detail": {
                    "tier": tier,
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                },
            },
        )

    async def coordinator_plan_update(self, **kwargs: object) -> None:
        """Coordinator 计划更新事件（DOC-04）"""
        await self._http_post_with_retry("coordinator_plan_update", dict(kwargs))

    async def run_complete(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cache_creation_tokens: int = 0,
        turn_count: int = 0,
    ) -> None:
        """Run 正常完成事件（HTTP 带重试）"""
        await self._http_post_with_retry(
            "run_complete",
            {
                "run_id": self._run_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_hit_tokens": cache_hit_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "turn_count": turn_count,
            },
        )

    async def run_error(self, error: str) -> None:
        """Run 异常终止事件（HTTP 带重试）"""
        await self._http_post_with_retry(
            "run_error",
            {
                "run_id": self._run_id,
                "error": error,
            },
        )

    async def close(self) -> None:
        """释放 httpx + Redis 连接"""
        await self._client.aclose()
        await self._redis.aclose()
