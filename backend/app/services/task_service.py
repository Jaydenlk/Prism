"""
Prism v2 — 任务提交逻辑 (DOC-07 Task 7.2)

POST /tasks 核心处理流程：
  1. 如果 session_id 为 None → 创建新 Session
  2. 校验 Session 属于当前用户（铁律 4）
  3. 如果 Session 空闲（blocking_run_id=None）→ 立即执行
  4. 如果 Session 繁忙（有 blocking_run）→ 入队

所有状态变更在单个 DB 事务中完成；
子进程启动在事务提交后执行（避免事务回滚但子进程已启动的不一致）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.run import Run
from app.models.session import Session as SessionModel, SessionQueueItem
from app.schemas.task import SubmitTaskRequest, SubmitTaskResponse
from app.services.sequence_service import get_next_queue_sequence_no

# 队列最大长度保护（防止恶意爆填）
QUEUE_MAX_SIZE: int = 50

# Run 的默认 model（从 session.config_snapshot 读取，不存在则用此值）
DEFAULT_MODEL: str = "claude-sonnet-4-6-20251101"


class TaskService:
    """
    任务提交服务。

    每个请求创建一个实例（请求级生命周期），不共享状态。
    """

    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, user_id: str, data: SubmitTaskRequest) -> SubmitTaskResponse:
        """
        提交任务。

        事务边界：此方法内所有 DB 操作在同一事务中，调用方负责最终 commit。
        子进程启动在调用方 commit 后执行。

        Returns: SubmitTaskResponse
          - accepted_type="immediate"    → 立即执行（caller 启动子进程）
          - accepted_type="queued_query" → 已排队（caller 无需启动子进程）
        """
        # 1. 确定 Session
        if data.session_id is None:
            session = self._create_session(user_id)
        else:
            session = self._get_user_session(user_id, data.session_id)

        # 2. 判断立即执行 or 排队
        if session.blocking_run_id is None:
            return self._submit_immediate(session, user_id, data)
        else:
            return self._submit_queued(session, data.prompt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_session(self, user_id: str) -> SessionModel:
        """自动创建新 Session（session_id=None 时）。"""
        session = SessionModel(
            user_id=user_id,
            title=None,
            status="idle",
            config_snapshot={},
        )
        self._db.add(session)
        self._db.flush()  # 获取 session.id
        return session

    def _get_user_session(self, user_id: str, session_id: str) -> SessionModel:
        """获取 Session，铁律 4：校验 user_id 归属。"""
        session = self._db.get(SessionModel, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        return session

    def _resolve_model(self, session: SessionModel) -> str:
        """从 session.config_snapshot 读取 model，不存在则用默认值。"""
        return session.config_snapshot.get("model", DEFAULT_MODEL)

    def _resolve_provider_id(self, session: SessionModel) -> str | None:
        """从 session.config_snapshot 读取 provider_id，可为 None。"""
        return session.config_snapshot.get("provider_id", None)

    def _create_run(
        self,
        session: SessionModel,
        user_id: str,
        data: SubmitTaskRequest,
        schedule_mode: str = "immediate",
    ) -> Run:
        """创建 Run 记录并 flush 以获取 id。"""
        run = Run(
            session_id=session.id,
            user_id=user_id,
            prompt=data.prompt,
            status="pending",
            model=self._resolve_model(session),
            provider_id=self._resolve_provider_id(session),
            agent_type=data.agent_type,
            schedule_mode=schedule_mode,
        )
        self._db.add(run)
        self._db.flush()  # 获取 run.id
        return run

    def _submit_immediate(
        self,
        session: SessionModel,
        user_id: str,
        data: SubmitTaskRequest,
    ) -> SubmitTaskResponse:
        """Session 空闲：创建 Run + 阻塞 Session。"""
        run = self._create_run(session, user_id, data, schedule_mode="immediate")

        session.blocking_run_id = run.id
        session.status = "running"
        self._db.flush()

        return SubmitTaskResponse(
            session_id=session.id,
            run_id=run.id,
            accepted_type="immediate",
            queue_position=None,
        )

    def _submit_queued(self, session: SessionModel, prompt: str) -> SubmitTaskResponse:
        """Session 繁忙：入队。"""
        queue_size = self._get_queue_size(session.id)
        if queue_size >= QUEUE_MAX_SIZE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Session queue is full ({QUEUE_MAX_SIZE} items max)",
            )

        # ADR-060：sequence_no 原子分配（advisory_xact_lock 方案）
        seq_no = get_next_queue_sequence_no(self._db, session.id)

        queue_item = SessionQueueItem(
            session_id=session.id,
            prompt=prompt,
            status="queued",
            sequence_no=seq_no,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(queue_item)
        self._db.flush()

        return SubmitTaskResponse(
            session_id=session.id,
            run_id=None,
            accepted_type="queued_query",
            queue_position=seq_no,
        )

    def _get_queue_size(self, session_id: str) -> int:
        """当前队列中 status=queued 的数量。"""
        return (
            self._db.query(SessionQueueItem)
            .filter(
                SessionQueueItem.session_id == session_id,
                SessionQueueItem.status == "queued",
            )
            .count()
        )
