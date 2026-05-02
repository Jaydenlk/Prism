"""
Prism v2 — 内部回调端点 (DOC-07 Task 7.3, ADR-063)

POST /api/v1/internal/callbacks
  认证: X-Callback-Secret header（不经过 JWT，不走 get_current_user）
  处理: CLI 子进程 → Backend 关键事件（tool_start/tool_end/message_complete/
        run_complete/run_error/permission_ask/harness_event/coordinator_plan_update）

POST /api/v1/internal/run-crashed (v4 新增)
  认证: X-Callback-Secret header（internal-only）
  处理: HeartbeatMonitor 或 subprocess supervisor 直接调用，标记 Run crashed + promote

安全约束：
  - CALLBACK_SECRET 与 JWT_SECRET / ENCRYPTION_KEY 严格独立（ADR-004）
  - 所有端点 include_in_schema=False（不暴露在 Swagger UI）
  - 幂等：run_complete/run_error 内部 RunLifecycle 幂等处理

事务约定（ADR-063）：
  - handle_callback：CallbackService.handle() 同步执行，统一 db.commit()
  - 若 promote 了新 Run，返回 promoted_run_id（调用方 DOC-07 Task 7.4 负责启动子进程）
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decrypt_value
from app.models.mcp_server import McpServer, UserMcpInstall
from app.models.skill_install import SkillInstall
from app.services.callback_service import CallbackService
from app.services.run_lifecycle import RunLifecycle
from app.services.sse_manager import SSEManager

import structlog
logger = structlog.get_logger()

router = APIRouter(prefix="/internal", tags=["internal"])


# ---------------------------------------------------------------------------
# Dependency: verify CALLBACK_SECRET
# ---------------------------------------------------------------------------

def _verify_callback_secret(
    x_callback_secret: str = Header(..., alias="X-Callback-Secret"),
) -> None:
    """
    校验 X-Callback-Secret header（ADR-004 三密钥独立）。

    Raises:
        HTTPException 403 — secret 不匹配时拒绝请求。
    """
    if x_callback_secret != settings.CALLBACK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid callback secret",
        )


# ---------------------------------------------------------------------------
# POST /internal/callbacks — 主回调端点
# ---------------------------------------------------------------------------

@router.post(
    "/callbacks",
    include_in_schema=False,
    status_code=200,
)
async def handle_callback(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, Any]:
    """
    处理 CLI 子进程发出的关键事件回调（ADR-063 方案 A HTTP 侧）。

    认证：X-Callback-Secret header 必须匹配 CALLBACK_SECRET。

    支持的 event_type（完整列表见 callback_service.py）：
      - text_delta          : SSE forward only
      - tool_start          : 创建 ToolExecution + tool_use Message
      - tool_end            : 更新 ToolExecution + tool_result Message
      - message_complete    : 写完整 assistant Message
      - run_complete        : RunLifecycle.complete_and_promote()
      - run_error           : RunLifecycle.fail_and_promote()
      - permission_ask      : INSERT permission_requests + SSE
      - harness_event       : INSERT audit_logs + SSE
      - coordinator_plan_update : UPSERT coordinator_plans
      - session_title       : UPDATE sessions.title

    幂等性：
      - tool_start/tool_end 通过 run_id+tool_name 防重
      - permission_ask 通过 request_id 防重
      - run_complete/run_error 通过 RunLifecycle 内部状态机防重

    返回：
      {"status": "ok"} 或 {"status": "error", "message": ..., "promoted_run_id": ...}
    """
    try:
        event: dict = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON payload: {exc}",
        )

    run_id = event.get("run_id", "")
    event_type = event.get("event_type", "")

    logger.debug(
        "callback.received",
        run_id=run_id,
        event_type=event_type,
    )

    sse = SSEManager(settings.REDIS_URL)
    service = CallbackService(db, sse, settings)
    result = service.handle(event)

    # 统一 commit（CallbackService 内部只 flush）
    # run_complete/run_error 内部的 RunLifecycle 已经 commit，
    # 此处 commit 幂等（空事务不报错）
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("callback.commit_failed", run_id=run_id, error=str(exc))
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database commit failed: {exc}",
        )

    # 启动 promoted run 的子进程（ADR-066 标准化参数）
    promoted_run_id = result.get("promoted_run_id")
    if promoted_run_id:
        logger.info(
            "callback.run_promoted",
            run_id=run_id,
            promoted_run_id=promoted_run_id,
        )
        # 从 app.state 获取 ProcessManager 单例，启动新子进程
        process_manager = getattr(request.app.state, "process_manager", None)
        if process_manager is not None:
            process_manager.start_run(promoted_run_id)
            logger.info(
                "callback.promoted_subprocess_started",
                promoted_run_id=promoted_run_id,
            )
        else:
            logger.warning(
                "callback.process_manager_unavailable",
                promoted_run_id=promoted_run_id,
                message="ProcessManager not in app.state; promoted run subprocess not started",
            )

    return result


# ---------------------------------------------------------------------------
# POST /internal/run-crashed — HeartbeatMonitor 触发的崩溃标记
# ---------------------------------------------------------------------------

@router.post(
    "/run-crashed",
    include_in_schema=False,
    status_code=200,
)
async def run_crashed(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, Any]:
    """
    v4 新增（ADR-065）：标记 Run crashed + promote 队列。

    由 HeartbeatMonitor 或外部 subprocess supervisor 调用。

    请求体：
      {"run_id": str, "reason": str}

    返回：
      {"success": true, "new_run_id": str | null}
    """
    try:
        body: dict = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON payload: {exc}",
        )

    run_id: str = body.get("run_id", "")
    reason: str = body.get("reason", "subprocess_crash")

    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="run_id is required",
        )

    logger.warning(
        "callback.run_crashed",
        run_id=run_id,
        reason=reason,
    )

    lifecycle = RunLifecycle(db)
    try:
        new_run_id = lifecycle.mark_crashed(run_id, reason=reason)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("callback.mark_crashed_failed", run_id=run_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return {"success": True, "new_run_id": new_run_id}


# ---------------------------------------------------------------------------
# GET /internal/users/{user_id}/installed-skills
# ---------------------------------------------------------------------------

@router.get(
    "/users/{user_id}/installed-skills",
    include_in_schema=False,
)
async def get_user_installed_skills(
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, list[dict[str, Any]]]:
    """
    Executor 启动期拉取 user-installed skills.

    返回结构: {"skills": [{"skill_name", "install_path", "source", "source_url", "version"}, ...]}
    """
    query = db.query(SkillInstall).filter(SkillInstall.user_id == user_id)
    if hasattr(SkillInstall, "status"):
        query = query.filter(SkillInstall.status == "installed")  # type: ignore[attr-defined]
    rows = query.all()
    return {
        "skills": [
            {
                "skill_name": r.skill_name,
                "install_path": getattr(r, "install_path", None),
                "source": r.source,
                "source_url": r.source_url,
                "version": r.version,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# GET /internal/users/{user_id}/mcp-servers
# ---------------------------------------------------------------------------

@router.get(
    "/users/{user_id}/mcp-servers",
    include_in_schema=False,
)
async def get_user_mcp_servers(
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, list[dict[str, Any]]]:
    """
    Executor 启动期拉取该 user 可用的 MCP servers (system-scope + user-installed user-scope).

    返回结构: {"servers": [{...row..., transport, headers (plaintext if http)}, ...]}
    HTTP 行的 headers_encrypted 在此处解密为 plaintext headers 字典.
    """
    system_rows = (
        db.query(McpServer)
        .filter(McpServer.scope == "system", McpServer.user_id.is_(None))
        .all()
    )
    user_rows = (
        db.query(McpServer)
        .join(UserMcpInstall, UserMcpInstall.mcp_server_id == McpServer.id)
        .filter(
            UserMcpInstall.user_id == user_id,
            UserMcpInstall.is_enabled.is_(True),
        )
        .all()
    )

    out: list[dict[str, Any]] = []
    for r in system_rows + user_rows:
        transport = getattr(r, "transport", "stdio")
        d: dict[str, Any] = {
            "id": r.id,
            "name": r.name,
            "scope": r.scope,
            "transport": transport,
            "command": r.command,
            "args": r.args,
            "env": r.env,
        }
        if transport == "http":
            d["url"] = getattr(r, "url", None)
            ciphertext = getattr(r, "headers_encrypted", None)
            d["headers"] = (
                json.loads(decrypt_value(ciphertext, settings.ENCRYPTION_KEY))
                if ciphertext
                else {}
            )
        out.append(d)
    return {"servers": out}
