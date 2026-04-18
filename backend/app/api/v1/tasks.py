"""
Prism v2 — Task API 端点 (DOC-07 Task 7.2)

路由表：
  POST   /tasks                          — 提交任务（核心入口）
  GET    /sessions/{id}/queue            — 获取队列消息
  DELETE /sessions/{id}/queue/{item_id}  — 取消排队消息
  POST   /runs/{id}/cancel               — 取消当前 Run（ADR-062 三模式）

设计要点：
  - POST /tasks 返回 202 Accepted（不论立即执行还是排队）
  - 子进程启动在事务 commit 后异步执行（Task 7.4 实现 _start_agent_subprocess）
  - 铁律 4：所有操作强制校验 user_id 归属
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.run import CancelRunRequest
from app.schemas.task import SubmitTaskRequest, SubmitTaskResponse
from app.services.run_lifecycle import RunLifecycle
from app.services.session_queue import SessionQueueService
from app.services.task_service import TaskService

router = APIRouter(tags=["tasks"])


# ---------------------------------------------------------------------------
# Placeholder — 子进程启动将在 Task 7.4 实现
# ---------------------------------------------------------------------------

def _start_agent_subprocess(run_id: str) -> None:
    """
    启动 Executor CLI 子进程（Task 7.4 实现）。

    此函数在事务 commit 后调用，保证 Run 记录已落库后再启动进程。
    当前为 stub，Task 7.4 将替换为完整实现。
    """
    # TODO(Task 7.4): 启动 CLI executor 子进程，传入 run_id + 标准化参数
    pass


# ---------------------------------------------------------------------------
# POST /tasks — 提交任务
# ---------------------------------------------------------------------------

@router.post(
    "/tasks",
    response_model=ApiResponse[SubmitTaskResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交任务（核心入口）",
)
def submit_task(
    data: SubmitTaskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[SubmitTaskResponse]:
    """
    提交任务。

    - `accepted_type="immediate"`: session 空闲，立即创建 Run 并启动子进程
    - `accepted_type="queued_query"`: session 繁忙，已加入队列

    202 Accepted 表示任务已接受，不代表已完成执行。
    """
    result = TaskService(db, settings).submit(user.id, data)
    db.commit()

    if result.accepted_type == "immediate" and result.run_id:
        # 事务已提交，安全启动子进程（Task 7.4 实现）
        _start_agent_subprocess(result.run_id)

    return ApiResponse(data=result)


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/queue — 获取队列消息
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/queue",
    response_model=ApiResponse[list[dict]],
    summary="获取 Session 队列消息",
)
def get_session_queue(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """
    获取 Session 当前排队中的消息列表（status=queued），按 sequence_no 升序。
    """
    svc = SessionQueueService(db)
    items = svc.list_queue(user.id, session_id)
    return ApiResponse(
        data=[
            {
                "id": item.id,
                "session_id": item.session_id,
                "prompt": item.prompt,
                "status": item.status,
                "sequence_no": item.sequence_no,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ]
    )


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}/queue/{item_id} — 取消排队消息
# ---------------------------------------------------------------------------

@router.delete(
    "/sessions/{session_id}/queue/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="取消排队消息",
)
def cancel_queue_item(
    session_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """
    取消排队中的消息（标记 cancelled，不物理删除）。
    只能取消 status=queued 的 item；其他状态返回 409。
    """
    SessionQueueService(db).cancel_item(user.id, session_id, item_id)


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/cancel — 取消 Run（ADR-062 三模式）
# ---------------------------------------------------------------------------

@router.post(
    "/runs/{run_id}/cancel",
    response_model=ApiResponse[dict],
    summary="取消 Run（三模式：graceful / force / also_cancel_queue）",
)
def cancel_run(
    run_id: str,
    data: CancelRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """
    取消 Run（v4 ADR-062）。

    mode:
      - `graceful`          (默认) SIGTERM，子进程完成当前 tool 后 break
      - `force`             SIGKILL，立即终止
      - `also_cancel_queue` graceful 当前 + 取消所有后续队列 item
    """
    RunLifecycle(db).cancel(run_id, mode=data.mode, user_id=user.id)
    return ApiResponse(data={"run_id": run_id, "mode": data.mode, "status": "cancel_requested"})
