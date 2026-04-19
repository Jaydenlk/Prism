"""
Prism v2 — Coordinator Recovery Service (DOC-07 Task 7.4, ADR-067)

POST /runs/{id}/resume 流程：
  1. 校验当前 run 是 failed + error_message 含 "heartbeat_stale"
     （只允许恢复心跳超时崩溃的 Run，非崩溃类失败不允许 resume）
  2. 查 coordinator_plans 表，取最新 checkpoint
     SELECT plan_json, current_step_index FROM coordinator_plans WHERE run_id=X
  3. 新建 Run（继承 session_id / user_id / prompt / model / provider_id）
  4. 将 coordinator_plans.run_id 更新为新 Run ID
  5. 启动子进程，传 --resume-from-step=current_step_index（ADR-066）

子进程启动后：
  executor/__main__.py 收到 --resume-from-step 后调用
  Coordinator.resume_from_checkpoint(DOC-04 v4 Task 4.3 已实现)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from app.models.coordinator_plan import CoordinatorPlan
from app.models.run import Run

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.services.process_manager import ProcessManager

import structlog
logger = structlog.get_logger()


class CoordinatorRecoveryService:
    """
    从 coordinator_plans checkpoint 恢复崩溃的 Run（ADR-067）。

    只处理两种情况：
      - HeartbeatMonitor 标记 crashed（error_message 含 "heartbeat_stale"）
      - run_crashed 端点标记的崩溃（error_message 含 "heartbeat_stale"）

    其他失败状态（用户取消 / 逻辑错误 / 超时）不允许通过此端点恢复。
    """

    def __init__(
        self,
        db: "Session",
        process_manager: "ProcessManager",
        settings: "Settings",
    ) -> None:
        self._db = db
        self._pm = process_manager
        self._settings = settings

    def resume(self, run_id: str, user_id: str) -> str:
        """
        恢复崩溃的 Run。

        Args:
            run_id:  原崩溃 Run 的 UUID。
            user_id: 当前用户 ID（铁律 4 归属校验）。

        Returns:
            新 Run 的 UUID（已提交到 DB，子进程已提交启动任务）。

        Raises:
            HTTPException 404 — Run 不存在 / 不属于该用户。
            HTTPException 409 — Run 不是 crashed 状态，或无 coordinator checkpoint。
        """
        # 1. 校验 Run 归属和状态（铁律 4）
        run = (
            self._db.query(Run)
            .filter(Run.id == run_id, Run.user_id == user_id)
            .first()
        )
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # 只允许恢复 failed + heartbeat_stale 的 Run
        if run.status != "failed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Run {run_id} cannot be resumed: "
                    f"status is '{run.status}', expected 'failed'"
                ),
            )
        error_msg = run.error_message or ""
        if "heartbeat_stale" not in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Run {run_id} cannot be resumed: "
                    "only runs crashed by heartbeat timeout are eligible"
                ),
            )

        # 2. 查 coordinator_plans checkpoint
        plan = (
            self._db.query(CoordinatorPlan)
            .filter(CoordinatorPlan.run_id == run_id)
            .order_by(CoordinatorPlan.updated_at.desc())
            .first()
        )
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No coordinator checkpoint found for run {run_id}",
            )

        resume_step = plan.current_step_index
        logger.info(
            "coordinator_recovery.resume_start",
            original_run_id=run_id,
            resume_step=resume_step,
        )

        # 3. 新建 Run（继承 session/user/prompt/model/provider）
        new_run = Run(
            session_id=run.session_id,
            user_id=run.user_id,
            prompt=run.prompt,
            status="pending",
            model=run.model,
            provider_id=run.provider_id,
            schedule_mode="resumed",
            agent_type=run.agent_type,
        )
        self._db.add(new_run)
        self._db.flush()  # 获取 new_run.id

        # 4. 将 coordinator_plans.run_id 更新为新 Run（checkpoint 跟随新 Run）
        plan.run_id = new_run.id
        self._db.commit()

        logger.info(
            "coordinator_recovery.new_run_created",
            original_run_id=run_id,
            new_run_id=new_run.id,
            resume_step=resume_step,
        )

        # 5. 启动子进程，传 --resume-from-step
        self._pm.start_run(new_run.id, resume_from_step=resume_step)

        logger.info(
            "coordinator_recovery.subprocess_launched",
            new_run_id=new_run.id,
            resume_step=resume_step,
        )

        return new_run.id
