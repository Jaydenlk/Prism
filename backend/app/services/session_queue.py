"""
Prism v2 — Session 排队管理 (DOC-07 Task 7.2)

简单 FIFO 队列，附加在 Session 上。
提供队列查询、单条取消、队列大小等只读/轻量操作。

重量级操作（promote_next）在 RunLifecycle 中执行以保证原子性（ADR-061）。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel, SessionQueueItem


class SessionQueueService:
    """Session 排队服务（请求级生命周期）。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user_session(self, user_id: str, session_id: str) -> SessionModel:
        """铁律 4：校验 Session 归属。"""
        session = self._db.get(SessionModel, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        return session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_queue(
        self,
        user_id: str,
        session_id: str,
    ) -> list[SessionQueueItem]:
        """
        列出排队消息（status=queued），按 sequence_no 升序。

        铁律 4：先校验 session 属于当前用户。
        """
        self._get_user_session(user_id, session_id)

        return (
            self._db.query(SessionQueueItem)
            .filter(
                SessionQueueItem.session_id == session_id,
                SessionQueueItem.status == "queued",
            )
            .order_by(SessionQueueItem.sequence_no)
            .all()
        )

    def cancel_item(
        self,
        user_id: str,
        session_id: str,
        item_id: str,
    ) -> None:
        """
        取消排队消息（标记 cancelled，不物理删除）。

        铁律 4：校验 session 归属 + item 归属于该 session。
        只能取消 status=queued 的 item；其他状态返回 409。
        """
        self._get_user_session(user_id, session_id)

        item = self._db.get(SessionQueueItem, item_id)
        if item is None or item.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue item {item_id} not found",
            )

        if item.status != "queued":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Queue item {item_id} is not in queued state (current: {item.status})",
            )

        item.status = "cancelled"
        self._db.commit()

    def get_queue_size(self, session_id: str) -> int:
        """获取当前队列大小（status=queued 的数量）。"""
        return (
            self._db.query(SessionQueueItem)
            .filter(
                SessionQueueItem.session_id == session_id,
                SessionQueueItem.status == "queued",
            )
            .count()
        )
