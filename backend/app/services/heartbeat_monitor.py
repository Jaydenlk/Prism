"""
Prism v2 — HeartbeatMonitor (DOC-07 Task 7.3, ADR-065)

后台 Task：每 10s 扫描 Redis `harness:heartbeat:*`，
超过 30s 无心跳的 Run 标记 crashed + promote 队列。

生命周期：
  1. Backend lifespan 中 asyncio.create_task(monitor.run()) 启动
  2. FastAPI 关闭前调用 monitor.stop() 优雅退出

Redis key 格式：
  harness:heartbeat:{run_id}  → 值为 UNIX timestamp 字符串（子进程每 15s 更新）

崩溃判定：
  now() - int(value) > stale_threshold(30s) → 判定 crashed

副作用：
  1. RunLifecycle.mark_crashed(run_id, reason) — DB 标记 failed + promote
  2. DELETE harness:heartbeat:{run_id}          — 清理 key 避免重复处理
  3. Prometheus 计数器 +1

ADR-065 严格执行：scan_interval=10, stale_threshold=30（可通过构造函数覆盖）
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:

    from app.services.alert_dispatcher import AlertDispatcher
    from app.services.run_lifecycle import RunLifecycle

logger = structlog.get_logger(__name__)


class HeartbeatMonitor:
    """
    扫描僵尸 Run 的后台 Task（v4 ADR-065）。

    调用约定：
      monitor = HeartbeatMonitor(redis_client, lifecycle)
      task = asyncio.create_task(monitor.run())
      # 关闭时：
      monitor.stop()
      await task
    """

    def __init__(
        self,
        redis_client,              # redis.asyncio.Redis
        lifecycle: "RunLifecycle",
        scan_interval: int = 10,   # 扫描间隔，秒
        stale_threshold: int = 30, # 超过此秒数判定为 crashed
        alert_dispatcher: "AlertDispatcher | None" = None,  # ADR-120
    ) -> None:
        self._redis = redis_client
        self._lifecycle = lifecycle
        self._scan_interval = scan_interval
        self._stale_threshold = stale_threshold
        self._running = False
        self._alert_dispatcher = alert_dispatcher  # ADR-120 optional

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        后台循环，在 FastAPI lifespan 中以 asyncio.create_task 启动。

        异常不会中断循环，仅记录 ERROR 日志。
        """
        self._running = True
        logger.info(
            "heartbeat_monitor.started",
            scan_interval=self._scan_interval,
            stale_threshold=self._stale_threshold,
        )
        while self._running:
            try:
                await self._scan_once()
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "heartbeat_monitor.scan_failed",
                    error=str(exc),
                    exc_info=True,
                )
            await asyncio.sleep(self._scan_interval)
        logger.info("heartbeat_monitor.stopped")

    def stop(self) -> None:
        """通知后台循环在下一轮 sleep 后退出。"""
        self._running = False

    # ------------------------------------------------------------------
    # Core scan
    # ------------------------------------------------------------------

    async def _scan_once(self) -> None:
        """
        一次完整 SCAN 遍历：
          1. SCAN harness:heartbeat:*（分批，避免阻塞 Redis）
          2. 对每个 key 检查 age
          3. age > stale_threshold → mark_crashed + DELETE key
        """
        cursor: int = 0
        now: int = int(time.time())

        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor,
                match="harness:heartbeat:*",
                count=100,
            )

            for raw_key in keys:
                await self._handle_key(raw_key, now)

            if cursor == 0:
                break

    async def _handle_key(self, raw_key: bytes, now: int) -> None:
        """
        处理单个 heartbeat key。

        参数：
            raw_key : bytes，形如 b"harness:heartbeat:{run_id}"
            now     : 当前 UNIX timestamp
        """
        last_beat_raw: bytes | None = await self._redis.get(raw_key)
        if last_beat_raw is None:
            # key 已过期或被其他协程删除，忽略
            return

        try:
            age = now - int(last_beat_raw)
        except (ValueError, TypeError):
            logger.warning(
                "heartbeat_monitor.invalid_value",
                key=raw_key,
                value=last_beat_raw,
            )
            return

        if age <= self._stale_threshold:
            return  # 心跳正常，跳过

        # 提取 run_id
        if isinstance(raw_key, bytes):
            key_str = raw_key.decode("utf-8", errors="replace")
        else:
            key_str = str(raw_key)

        prefix = "harness:heartbeat:"
        if not key_str.startswith(prefix):
            return
        run_id = key_str[len(prefix):]

        logger.warning(
            "heartbeat_monitor.stale_detected",
            run_id=run_id,
            age_seconds=age,
        )

        # 标记 crashed + promote 队列（DB 操作在 lifecycle 内 commit）
        new_run_id = None
        try:
            new_run_id = self._lifecycle.mark_crashed(
                run_id, reason=f"heartbeat_stale_{age}s"
            )
            logger.info(
                "heartbeat_monitor.crashed_marked",
                run_id=run_id,
                new_run_id=new_run_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "heartbeat_monitor.mark_crashed_failed",
                run_id=run_id,
                error=str(exc),
            )

        # AlertDispatcher — critical 告警（ADR-120 PRD Part B §5）
        if self._alert_dispatcher is not None:
            try:
                await self._alert_dispatcher.dispatch(
                    severity="critical",
                    event_type="run.crashed",
                    detail={
                        "run_id": run_id,
                        "age_seconds": age,
                        "reason": f"heartbeat_stale_{age}s",
                        "promoted_run_id": new_run_id,
                    },
                    resource_type="run",
                    resource_id=run_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "heartbeat_monitor.alert_dispatcher_failed",
                    run_id=run_id,
                    error=str(exc),
                )

        # 清除 key 避免重复处理（即使 mark_crashed 失败也删除）
        await self._redis.delete(raw_key)

        # Prometheus（容忍 ImportError，metrics 在 DOC-12 完整实现）
        try:
            from app.observability.metrics import REGISTRY

            # 懒加载计数器（避免在 DOC-12 前要求 metrics 完整存在）
            _stale_counter = _get_or_create_counter(
                "prism_agent_heartbeat_stale_total",
                "Total stale heartbeat detections",
                [],
                REGISTRY,
            )
            _stale_counter.inc()
        except Exception:  # noqa: BLE001
            pass  # metrics 未就绪时静默降级


# ---------------------------------------------------------------------------
# Prometheus counter lazy-init helper
# ---------------------------------------------------------------------------

_counter_cache: dict[str, object] = {}


def _get_or_create_counter(name: str, doc: str, labels: list, registry) -> object:
    """
    懒加载 Prometheus Counter，防止重复注册导致的 ValueError。
    """
    if name not in _counter_cache:
        from prometheus_client import Counter
        try:
            c = Counter(name, doc, labels, registry=registry)
        except ValueError:
            # 已注册（测试环境多次 import）
            from prometheus_client import REGISTRY as DEFAULT_REGISTRY
            c = DEFAULT_REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        _counter_cache[name] = c
    return _counter_cache[name]
