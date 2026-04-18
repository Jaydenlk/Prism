"""
Prism v2 — Run API 端点 (DOC-07 Task 7.2 / Task 7.4)

路由表：
  GET  /runs/{id}            — Run 详情（含 harness_summary JSONB）
  GET  /sessions/{id}/runs   — Session 下的 Run 列表
  POST /runs/{id}/resume     — v4 ADR-067: coordinator_recovery 从 checkpoint 重启

铁律 4：所有查询强制校验 user_id 归属。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PagedResponse
from app.schemas.run import RunListResponse, RunResponse
from app.services.run_lifecycle import RunLifecycle

router = APIRouter(tags=["runs"])


def _run_to_response(run) -> RunResponse:
    """ORM Run → RunResponse Pydantic schema 转换。"""
    return RunResponse(
        id=run.id,
        session_id=run.session_id,
        prompt=run.prompt,
        status=run.status,
        model=run.model,
        provider_id=run.provider_id,
        schedule_mode=run.schedule_mode,
        agent_type=getattr(run, "agent_type", None),
        error_message=run.error_message,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        cost_usd=float(run.cost_usd) if run.cost_usd is not None else None,
        turn_count=run.turn_count,
        harness_summary=run.harness_summary,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


def _run_to_list_response(run) -> RunListResponse:
    """ORM Run → RunListResponse 精简版转换。"""
    return RunListResponse(
        id=run.id,
        status=run.status,
        prompt=run.prompt,
        agent_type=getattr(run, "agent_type", None),
        turn_count=run.turn_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


# ---------------------------------------------------------------------------
# GET /runs/{run_id} — Run 详情
# ---------------------------------------------------------------------------

@router.get(
    "/runs/{run_id}",
    response_model=ApiResponse[RunResponse],
    summary="获取 Run 详情（含 harness_summary）",
)
def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[RunResponse]:
    """
    获取 Run 详情，含 harness_summary JSONB（DOC-07 前置定义 schema）。
    铁律 4：Run 必须属于当前用户。
    """
    lifecycle = RunLifecycle(db)
    run = lifecycle.get_run(run_id, user_id=user.id)
    return ApiResponse(data=_run_to_response(run))


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/runs — Session 下的 Run 列表
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/runs",
    response_model=ApiResponse[PagedResponse[RunListResponse]],
    summary="获取 Session 下的 Run 列表",
)
def list_session_runs(
    session_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PagedResponse[RunListResponse]]:
    """
    获取 Session 下的 Run 列表，按 created_at DESC 排序。
    铁律 4：Session 必须属于当前用户。
    """
    lifecycle = RunLifecycle(db)
    offset = (page - 1) * per_page
    runs, total = lifecycle.list_runs_for_session(
        user_id=user.id,
        session_id=session_id,
        limit=per_page,
        offset=offset,
    )
    items = [_run_to_list_response(r) for r in runs]
    paged = PagedResponse.from_query(items, total, page, per_page)
    return ApiResponse(data=paged)


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/resume — Coordinator Recovery（ADR-067）
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/resume",
    response_model=ApiResponse[dict],
    summary="从 coordinator checkpoint 恢复崩溃的 Run（ADR-067）",
)
def resume_run(
    run_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[dict]:
    """
    v4 ADR-067: 从 coordinator_plans 表读 checkpoint 重启崩溃的 Run。

    适用场景：
      - Run status='failed' + error_message 含 'heartbeat_stale'
      - coordinator_plans 表有对应 checkpoint（current_step_index）

    成功时：
      - 创建新 Run（继承原 Run 的 session/model/provider/prompt）
      - 启动子进程，传 --resume-from-step=N
      - 返回 {"new_run_id": "..."}

    错误时：
      - 404: Run 不存在或无 checkpoint
      - 409: Run 状态不符合恢复条件
    """
    from app.services.coordinator_recovery import CoordinatorRecoveryService

    # 从 app.state 获取 ProcessManager（lifespan 中注册）
    process_manager = getattr(request.app.state, "process_manager", None)
    if process_manager is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="ProcessManager not available (service starting up)",
        )

    svc = CoordinatorRecoveryService(
        db=db,
        process_manager=process_manager,
        settings=settings,
    )
    new_run_id = svc.resume(run_id=run_id, user_id=user.id)
    return ApiResponse(data={"original_run_id": run_id, "new_run_id": new_run_id})
