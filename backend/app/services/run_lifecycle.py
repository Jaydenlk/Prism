"""
Prism v2 — Run 生命周期状态机 + promote (DOC-07 Task 7.2)

⚠️ 审计关注点（ADR-061）：
   promote_next() 必须在单个 DB 事务中原子完成：
     1. 旧 Run 标记 completed/failed
     2. session.blocking_run_id = None, session.status = "idle"
     3. SELECT ... FOR UPDATE SKIP LOCKED 查 session_queue_items
     4. 新 Run 创建 + session 重新阻塞
   全部 commit 后才可启动子进程。

状态转换：
  pending  → running   （子进程启动成功时）
  running  → completed （正常完成，via complete_and_promote）
  running  → failed    （执行异常，via fail_and_promote）
  running  → timeout   （超时 kill，via timeout）
  running  → cancelled （用户取消，via cancel，ADR-062 三模式）
  pending  → cancelled （子进程启动前取消，via cancel）
  running  → failed    （HeartbeatMonitor 崩溃检测，via mark_crashed，ADR-065）
"""
from __future__ import annotations

import os
import signal
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.run import Run
from app.models.session import Session as SessionModel, SessionQueueItem

if TYPE_CHECKING:
    pass


class RunLifecycle:
    """
    Run 生命周期管理器。

    调用方约定：
      - 每次操作前 **不** 需要手动 begin()；Service 内部管理 flush/commit。
      - 禁止从 API 路由层直接调用 db.commit()（P1 规则）。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_run(self, run_id: str) -> Run:
        run = self._db.get(Run, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )
        return run

    def _get_session(self, session_id: str) -> SessionModel:
        sess = self._db.get(SessionModel, session_id)
        if sess is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        return sess

    def _promote_next(self, completed_run: Run) -> str | None:
        """
        内部 promote 逻辑。在已开启的事务中调用。

        用 FOR UPDATE SKIP LOCKED 防并发重复 promote。
        返回新创建的 run_id（如无队列 item 则返回 None）。
        """
        session = self._get_session(completed_run.session_id)

        # 解除 Session 阻塞
        session.blocking_run_id = None
        session.status = "idle"

        # 查找队列中下一条（SKIP LOCKED 防并发）
        next_item: SessionQueueItem | None = (
            self._db.query(SessionQueueItem)
            .filter(
                SessionQueueItem.session_id == session.id,
                SessionQueueItem.status == "queued",
            )
            .order_by(SessionQueueItem.sequence_no)
            .with_for_update(skip_locked=True)
            .first()
        )

        new_run_id: str | None = None
        if next_item is not None:
            # 标记 promoted
            next_item.status = "promoted"

            # 创建新 Run（继承上一次的 model/provider_id 配置）
            new_run = Run(
                session_id=session.id,
                user_id=completed_run.user_id,
                prompt=next_item.prompt,
                status="pending",
                model=completed_run.model,
                provider_id=completed_run.provider_id,
                schedule_mode="queued",
            )
            self._db.add(new_run)
            self._db.flush()  # 获取 new_run.id

            # 重新阻塞 Session
            session.blocking_run_id = new_run.id
            session.status = "running"
            new_run_id = new_run.id

        return new_run_id

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_running(self, run_id: str) -> None:
        """
        子进程启动成功后调用。
        pending → running
        """
        run = self._get_run(run_id)
        if run.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {run_id} is not in pending state (current: {run.status})",
            )
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        self._db.flush()

    def complete_and_promote(
        self,
        run_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        turn_count: int = 0,
        harness_summary: dict | None = None,
    ) -> str | None:
        """
        标记 Run completed 并原子性推进队列（ADR-061）。

        ⚠️ 整个方法在一个 DB 事务中执行（单次 commit）。
        返回：新创建的 run_id（如有队列消息被 promote），否则 None。
        事务 commit 后，调用方负责启动新子进程（如有 new_run_id）。
        """
        run = self._get_run(run_id)

        # 1. 标记 Run 完成
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.cost_usd = cost_usd
        run.turn_count = turn_count
        run.harness_summary = harness_summary or {}

        # 2-6. promote（Session 解锁 + FOR UPDATE SKIP LOCKED + 新 Run）
        new_run_id = self._promote_next(run)

        self._db.commit()
        return new_run_id

    def fail_and_promote(
        self,
        run_id: str,
        error: str,
        harness_summary: dict | None = None,
    ) -> str | None:
        """
        标记 Run failed 并推进队列。

        逻辑同 complete_and_promote，status 为 failed。
        """
        run = self._get_run(run_id)

        run.status = "failed"
        run.error_message = error
        run.finished_at = datetime.now(timezone.utc)
        run.harness_summary = harness_summary or {}

        new_run_id = self._promote_next(run)

        self._db.commit()
        return new_run_id

    def cancel(self, run_id: str, mode: str = "graceful", user_id: str | None = None) -> None:
        """
        取消 Run（v4 ADR-062 三模式）。

        mode:
          - "graceful"          SIGTERM → 子进程完成当前 tool 后 break TAOR 循环
          - "force"             SIGKILL → 立即终止
          - "also_cancel_queue" graceful 当前 + 所有后续 queue items 标记 cancelled

        运行前校验（如有 user_id 则做归属校验）。
        如果 status == "pending"：直接标记 cancelled（无子进程可 kill）。
        如果 status == "running"：按 mode 发信号。
        其他终态（completed/failed/cancelled）：返回 409 Conflict。
        """
        run = self._get_run(run_id)

        # 归属校验
        if user_id is not None and run.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # 终态检查
        if run.status in ("completed", "failed", "cancelled", "timeout"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {run_id} is already in terminal state: {run.status}",
            )

        if run.status == "pending":
            # 未启动，直接标记
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            self._db.commit()
            return

        # status == "running"
        if run.subprocess_pid:
            if mode == "force":
                try:
                    os.kill(run.subprocess_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # 进程已退出，继续更新 DB
            else:
                # graceful / also_cancel_queue 均先 SIGTERM
                try:
                    os.kill(run.subprocess_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

        if mode == "also_cancel_queue":
            # 把后续队列 item 全部标记 cancelled
            self._db.query(SessionQueueItem).filter(
                SessionQueueItem.session_id == run.session_id,
                SessionQueueItem.status == "queued",
            ).update({"status": "cancelled"})

        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)

        # 解除 Session 阻塞（cancelled run 不再 promote）
        session = self._get_session(run.session_id)
        if session.blocking_run_id == run.id:
            session.blocking_run_id = None
            session.status = "idle"

        self._db.commit()

    def mark_crashed(self, run_id: str, reason: str) -> str | None:
        """
        v4 ADR-065：HeartbeatMonitor 调用。

        标记 Run crashed（status=failed） + promote 队列中的下一条。
        返回新 run_id（如有），供调用方启动新子进程。
        """
        run = self._get_run(run_id)

        if run.status not in ("running", "pending"):
            # 已处于终态，幂等处理
            return None

        run.status = "failed"
        run.error_message = reason
        run.finished_at = datetime.now(timezone.utc)

        new_run_id = self._promote_next(run)

        self._db.commit()
        return new_run_id

    def timeout(self, run_id: str) -> str | None:
        """
        超时处理：kill 子进程 + 标记 timeout + promote 队列。

        Returns: 新 run_id（如有 promote），否则 None。
        """
        run = self._get_run(run_id)

        if run.status not in ("running", "pending"):
            return None

        # 尝试 SIGKILL 子进程
        if run.subprocess_pid:
            try:
                os.kill(run.subprocess_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        run.status = "failed"
        run.error_message = "Run timed out"
        run.finished_at = datetime.now(timezone.utc)

        new_run_id = self._promote_next(run)

        self._db.commit()
        return new_run_id

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_run(self, run_id: str, user_id: str | None = None) -> Run:
        """获取 Run，可选归属校验。"""
        run = self._get_run(run_id)
        if user_id is not None and run.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )
        return run

    def list_runs_for_session(
        self,
        user_id: str,
        session_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Run], int]:
        """
        获取 Session 下的 Run 列表。

        铁律 4：先校验 session 属于当前用户。
        """
        # 铁律 4：session 归属校验
        session = self._db.get(SessionModel, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        total: int = (
            self._db.query(Run)
            .filter(Run.session_id == session_id)
            .count()
        )
        runs: list[Run] = (
            self._db.query(Run)
            .filter(Run.session_id == session_id)
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return runs, total
