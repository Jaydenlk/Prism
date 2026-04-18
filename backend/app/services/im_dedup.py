"""
Prism v2 — IM Webhook 幂等服务 (DOC-08 Task 8.1, ADR-070)

策略：同一 (channel, msg_id) 在 7 天内只处理一次。

DB 方案（Phase 1 首选，便于审计）：
  - 尝试 INSERT im_message_dedup(channel, platform_message_id, received_at)
  - 命中唯一约束 → IntegrityError → 判定为重复 → 调用方 ignore
  - 未命中 → 记录已插入 → 调用方继续处理

可选 Redis 方案（高吞吐场景）：
  - SETNX im:dedup:{channel}:{msg_id} 1 EX 604800
  - 返回 0 → 已存在 → 重复
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.im_dedup import ImMessageDedup

logger = structlog.get_logger(__name__)


class IMDedupService:
    """
    IM Webhook 幂等服务（DB 方案，ADR-070）。

    使用方式：
        dedup = IMDedupService(db)
        if dedup.is_duplicate(channel="feishu", msg_id="om_xxx", session_id=None):
            return  # 已处理过，直接 ignore
        db.commit()
        # ... 继续处理消息 ...
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Core dedup
    # ------------------------------------------------------------------

    def is_duplicate(
        self,
        channel: str,
        msg_id: str,
        session_id: str | None = None,
    ) -> bool:
        """
        检查 (channel, msg_id) 是否已处理过。

        Returns:
            True  — 重复（已处理），调用方应直接返回 200 OK 让平台停止重试
            False — 首次，已记录 dedup 条目，调用方继续处理

        副作用：
            返回 False 时已执行 db.flush()，将 INSERT 写入当前事务；
            调用方需在业务逻辑完成后执行 db.commit()。
            返回 True 时会执行 db.rollback()（仅回滚 IntegrityError savepoint）。
        """
        record = ImMessageDedup(
            channel=channel,
            platform_message_id=msg_id,
            received_at=datetime.now(timezone.utc),
            session_id=session_id,
        )
        try:
            self._db.add(record)
            self._db.flush()  # 触发唯一约束检查（不提交事务）
            logger.debug(
                "im.dedup.recorded",
                channel=channel,
                msg_id=msg_id,
            )
            return False
        except IntegrityError:
            # 唯一约束冲突 → 重复消息
            self._db.rollback()
            logger.info(
                "im.message.duplicate",
                channel=channel,
                msg_id=msg_id,
            )
            return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_expired(self, days: int = 7) -> int:
        """
        清理过期 dedup 条目（应由 Cron/定时任务调用，非请求路径）。

        Returns:
            删除的记录数
        """
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = (
            self._db.query(ImMessageDedup)
            .filter(ImMessageDedup.received_at < threshold)
            .delete(synchronize_session=False)
        )
        self._db.commit()
        logger.info(
            "im.dedup.cleanup",
            days=days,
            deleted=deleted,
        )
        return deleted

    def update_session_id(
        self,
        channel: str,
        msg_id: str,
        session_id: str,
    ) -> bool:
        """
        路由成功后，将 session_id 回填到 dedup 记录（可选，增强可追溯性）。

        Returns:
            True — 更新成功；False — 记录不存在
        """
        updated = (
            self._db.query(ImMessageDedup)
            .filter(
                ImMessageDedup.channel == channel,
                ImMessageDedup.platform_message_id == msg_id,
            )
            .update({"session_id": session_id}, synchronize_session=False)
        )
        return updated > 0


# ---------------------------------------------------------------------------
# Optional: Redis-based dedup (Phase 1 高吞吐备选方案, ADR-070)
# ---------------------------------------------------------------------------

class IMDedupRedisService:
    """
    IM Webhook 幂等服务（Redis 方案，ADR-070 备选）。

    适合高吞吐场景（> 1000 msg/s），牺牲审计可追溯性。
    Phase 1 使用 IMDedupService（DB 方案）；此类预留给 Phase 2 按需切换。

    使用方式：
        dedup = IMDedupRedisService(redis_client)
        if await dedup.is_duplicate("feishu", "om_xxx"):
            return
        # 继续处理...
    """

    def __init__(self, redis_client, ttl_seconds: int = 604800) -> None:
        """
        Args:
            redis_client: redis.asyncio.Redis 实例
            ttl_seconds:  去重窗口（默认 7 天）
        """
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def is_duplicate(self, channel: str, msg_id: str) -> bool:
        """
        SETNX 原子去重。

        Returns:
            True  — 已存在（重复）
            False — 首次设置（继续处理）
        """
        key = f"im:dedup:{channel}:{msg_id}"
        # SET key value EX ttl NX — 返回 True 表示首次设置成功
        was_new = await self._redis.set(key, "1", ex=self._ttl, nx=True)
        if not was_new:
            logger.info(
                "im.message.duplicate",
                channel=channel,
                msg_id=msg_id,
                backend="redis",
            )
        return not was_new
