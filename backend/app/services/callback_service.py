"""
Prism v2 — Callback Service (DOC-07 Task 7.3, ADR-063)

处理 CLI 子进程通过 HTTP POST 发送的关键事件（方案 A 双通道中的 HTTP 侧）。

事件类型 → 处理逻辑：
  text_delta           → SSE forward only（不写 DB；Adapter 本地累积到 message_complete）
  tool_start           → 创建 ToolExecution 记录 + tool_use Message + SSE
  tool_end             → 更新 ToolExecution（output/duration_ms/is_error) + tool_result Message + SSE
  message_complete     → 创建完整 assistant Message（整条 content）+ SSE
  run_complete         → RunLifecycle.complete_and_promote() + SSE
  run_error            → RunLifecycle.fail_and_promote() + SSE
  permission_ask       → INSERT permission_requests + SSE（通知前端弹窗）
  harness_event        → INSERT audit_logs + SSE
  coordinator_plan_update → UPSERT coordinator_plans + SSE
  session_title        → UPDATE sessions.title + SSE

设计约束（ADR-063）：
  1. 所有 DB 操作同步执行（SQLAlchemy sync Session），handle() 本身 async 但 DB 写同步。
  2. 回调端点 handle_callback (internal.py) 在所有操作结束后统一 commit。
  3. text_delta 仅 SSE forward，不写 DB（Adapter 本地累积；message_complete 整条写）。
  4. 幂等设计：tool_start/tool_end 通过 tool_use_id 查重防止重复写。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.coordinator_plan import CoordinatorPlan
from app.models.message import Message
from app.models.permission_request import PermissionRequest
from app.models.run import Run
from app.models.tool_execution import ToolExecution
from app.services.run_lifecycle import RunLifecycle
from app.services.sequence_service import get_next_message_sequence_no
from app.services.sse_manager import SSEManager

import structlog
logger = structlog.get_logger()


class CallbackService:
    """
    处理 Agent 执行回调事件。

    所有 DB 操作在调用方事务中同步完成（handle() 结束后 caller commit）。
    SSE publish 通过 SSEManager 异步执行（fire-and-forget，不等待）。
    """

    def __init__(self, db: Session, sse: SSEManager, settings: Any) -> None:
        self._db = db
        self._sse = sse
        self._settings = settings

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, event: dict) -> dict:
        """
        处理单个回调事件（同步）。

        参数格式：
          {
            "run_id":     str,
            "event_type": str,
            "data":       dict,
            "timestamp":  str  (ISO-8601, optional)
          }

        返回：
          {"status": "ok"} 或 {"status": "error", "message": ..., "promoted_run_id": ...}

        ⚠️ DB commit 由调用方（internal.py 的 handle_callback）在 handle() 后统一执行。
        """
        run_id: str = event.get("run_id", "")
        event_type: str = event.get("event_type", "")
        data: dict = event.get("data", {})

        run: Run | None = self._db.get(Run, run_id)
        if run is None:
            logger.warning("callback.run_not_found", run_id=run_id, event_type=event_type)
            return {"status": "error", "message": f"Run not found: {run_id}"}

        handler = getattr(self, f"_handle_{event_type}", None)
        if handler is None:
            logger.warning("callback.unknown_event", event_type=event_type, run_id=run_id)
            return {"status": "error", "message": f"Unknown event type: {event_type}"}

        try:
            extra = handler(run, data) or {}
            return {"status": "ok", **extra}
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "callback.handler_failed",
                event_type=event_type,
                run_id=run_id,
                error=str(exc),
                exc_info=True,
            )
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # Event handlers（私有）
    # ------------------------------------------------------------------

    def _handle_text_delta(self, run: Run, data: dict) -> None:
        """
        文本流 delta — 仅 SSE forward，不写 DB（ADR-063）。

        Adapter 本地累积 text_delta；整条 assistant Message 在
        message_complete 事件时一次性写 DB。
        """
        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "text_delta", data)
        )

    def _handle_tool_start(self, run: Run, data: dict) -> None:
        """
        工具开始：创建 ToolExecution + tool_use Message。

        data 预期字段：
          tool_use_id  : str  (Anthropic tool_use block id)
          tool_name    : str
          tool_input   : dict
        """
        tool_use_id: str = data.get("tool_use_id", "")
        tool_name: str = data.get("tool_name", "unknown")
        tool_input: dict = data.get("tool_input", {})

        # 幂等：若 tool_use_id 已存在则跳过
        existing = (
            self._db.query(ToolExecution)
            .filter(
                ToolExecution.run_id == run.id,
                ToolExecution.tool_name == tool_name,
            )
            .first()
        )
        # 简单幂等：仅在 no prior execution found 时创建
        # （完整幂等需在 ToolExecution 追加 tool_use_id 字段，暂用 tool_name+run_id）

        te = ToolExecution(
            session_id=run.session_id,
            run_id=run.id,
            tool_name=tool_name,
            input=tool_input,
            is_error=False,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(te)
        self._db.flush()

        # tool_use message（content 含 tool_use block）
        seq_no = get_next_message_sequence_no(self._db, run.session_id)
        msg = Message(
            session_id=run.session_id,
            run_id=run.id,
            role="assistant",
            content=[
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": tool_input,
                }
            ],
            text_preview=f"[tool_use:{tool_name}]",
            sequence_no=seq_no,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(msg)
        self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "tool_start", {
                **data,
                "tool_execution_id": te.id,
                "message_id": msg.id,
            })
        )

    def _handle_tool_end(self, run: Run, data: dict) -> None:
        """
        工具结束：更新 ToolExecution + 创建 tool_result Message。

        data 预期字段：
          tool_use_id         : str
          tool_name           : str
          output              : dict | str
          is_error            : bool
          duration_ms         : int
          permission_decision : str | None
          hook_modified       : bool
        """
        tool_name: str = data.get("tool_name", "unknown")
        output: dict = data.get("output", {})
        is_error: bool = bool(data.get("is_error", False))
        duration_ms: int | None = data.get("duration_ms")
        permission_decision: str | None = data.get("permission_decision")
        hook_modified: bool = bool(data.get("hook_modified", False))
        tool_use_id: str = data.get("tool_use_id", "")

        # 更新最近一条同名 ToolExecution
        te: ToolExecution | None = (
            self._db.query(ToolExecution)
            .filter(
                ToolExecution.run_id == run.id,
                ToolExecution.tool_name == tool_name,
                ToolExecution.output.is_(None),  # 未填 output 的（即 tool_start 创建的）
            )
            .order_by(ToolExecution.created_at.desc())
            .first()
        )
        if te is not None:
            te.output = output if isinstance(output, dict) else {"result": str(output)}
            te.is_error = is_error
            te.duration_ms = duration_ms
            te.permission_decision = permission_decision
            te.hook_modified = hook_modified
            self._db.flush()

        # tool_result message
        seq_no = get_next_message_sequence_no(self._db, run.session_id)

        # content 格式：list of tool_result blocks
        if isinstance(output, dict):
            output_content = [{"type": "text", "text": str(output)}]
        else:
            output_content = [{"type": "text", "text": str(output)}]

        msg = Message(
            session_id=run.session_id,
            run_id=run.id,
            role="user",  # tool_result 属于 user 角色（Anthropic canonical）
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": output_content,
                    "is_error": is_error,
                }
            ],
            text_preview=f"[tool_result:{tool_name}]",
            sequence_no=seq_no,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(msg)
        self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "tool_end", {
                **data,
                "message_id": msg.id,
            })
        )

    def _handle_message_complete(self, run: Run, data: dict) -> None:
        """
        完整 assistant Message 落库（整条 content，Adapter 累积结束后发送）。

        data 预期字段：
          role    : str  (通常 "assistant")
          content : list (PrismMessage content blocks)
        """
        role: str = data.get("role", "assistant")
        content: list = data.get("content", [])

        # 生成 text_preview
        text_preview: str = _extract_text_preview(role, content)

        seq_no = get_next_message_sequence_no(self._db, run.session_id)
        msg = Message(
            session_id=run.session_id,
            run_id=run.id,
            role=role,
            content=content,
            text_preview=text_preview,
            sequence_no=seq_no,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(msg)
        self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "message_complete", {
                **data,
                "message_id": msg.id,
                "sequence_no": seq_no,
            })
        )

    def _handle_run_complete(self, run: Run, data: dict) -> dict:
        """
        Run 正常完成：RunLifecycle.complete_and_promote() + SSE。

        返回 {"promoted_run_id": new_run_id} 供 internal.py 启动新子进程。
        """
        lifecycle = RunLifecycle(self._db)
        new_run_id = lifecycle.complete_and_promote(
            run_id=run.id,
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cost_usd=data.get("cost_usd", 0.0),
            turn_count=data.get("turn_count", 0),
            harness_summary=data.get("harness_summary", {}),
        )

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "run_complete", data)
        )
        if new_run_id:
            asyncio.create_task(
                self._sse.publish(run.session_id, "queue_update", {
                    "promoted_run_id": new_run_id,
                })
            )

        return {"promoted_run_id": new_run_id}

    def _handle_run_error(self, run: Run, data: dict) -> dict:
        """
        Run 异常结束：RunLifecycle.fail_and_promote() + SSE。
        """
        lifecycle = RunLifecycle(self._db)
        new_run_id = lifecycle.fail_and_promote(
            run_id=run.id,
            error=data.get("error", "Unknown error"),
            harness_summary=data.get("harness_summary", {}),
        )

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "run_error", data)
        )
        if new_run_id:
            asyncio.create_task(
                self._sse.publish(run.session_id, "queue_update", {
                    "promoted_run_id": new_run_id,
                })
            )

        return {"promoted_run_id": new_run_id}

    def _handle_permission_ask(self, run: Run, data: dict) -> None:
        """
        权限请求：INSERT permission_requests + SSE 通知前端弹窗。

        data 预期字段：
          request_id  : str  (UUID4，子进程生成，与 perm_req:{id} Redis key 对应)
          tool_name   : str
          tool_input  : dict
          reason      : str
          timeout_at  : str  (ISO-8601)
        """
        request_id: str = data.get("request_id", "")
        tool_name: str = data.get("tool_name", "unknown")
        tool_input: dict = data.get("tool_input", {})
        reason: str = data.get("reason", "")
        timeout_at_str: str = data.get("timeout_at", "")

        # 解析 timeout_at
        try:
            timeout_at = datetime.fromisoformat(timeout_at_str)
        except (ValueError, TypeError):
            from datetime import timedelta
            timeout_at = datetime.now(timezone.utc) + timedelta(seconds=300)

        # 幂等：request_id 已存在则跳过
        existing = (
            self._db.query(PermissionRequest)
            .filter(PermissionRequest.request_id == request_id)
            .first()
        )
        if existing is None:
            pr = PermissionRequest(
                request_id=request_id,
                run_id=run.id,
                user_id=run.user_id,
                tool_name=tool_name,
                tool_input=tool_input,
                reason=reason,
                status="pending",
                requested_at=datetime.now(timezone.utc),
                timeout_at=timeout_at,
            )
            self._db.add(pr)
            self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "permission_ask", {
                **data,
                "run_id": run.id,
            })
        )

    def _handle_harness_event(self, run: Run, data: dict) -> None:
        """
        Harness 内部事件：INSERT audit_logs + SSE 推送。

        data 预期字段：
          type   : str  (heartbeat / permission_ask_timeout / loop_detected / ...)
          detail : dict (可选，事件详情)
        """
        event_type_name: str = data.get("type", "unknown")

        log = AuditLog(
            user_id=run.user_id,
            action=f"harness.{event_type_name}",
            resource_type="run",
            resource_id=run.id,
            details=data,
        )
        self._db.add(log)
        self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "harness_event", data)
        )

    def _handle_coordinator_plan_update(self, run: Run, data: dict) -> None:
        """
        Coordinator 计划 checkpoint：UPSERT coordinator_plans。

        data 预期字段：
          plan_json          : dict
          current_step_index : int
          step_results       : list
          status             : str  ("running" | "completed" | "failed")
        """
        plan_json: dict = data.get("plan_json", {})
        current_step_index: int = int(data.get("current_step_index", 0))
        step_results: list = data.get("step_results", [])
        status: str = data.get("status", "running")

        # UPSERT：以 run_id 查找，存在则更新，不存在则创建
        existing: CoordinatorPlan | None = (
            self._db.query(CoordinatorPlan)
            .filter(CoordinatorPlan.run_id == run.id)
            .first()
        )
        if existing is not None:
            existing.plan_json = plan_json
            existing.current_step_index = current_step_index
            existing.step_results = step_results
            existing.status = status
        else:
            plan = CoordinatorPlan(
                run_id=run.id,
                plan_json=plan_json,
                current_step_index=current_step_index,
                step_results=step_results,
                status=status,
            )
            self._db.add(plan)

        self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "coordinator_plan_update", data)
        )

    def _handle_session_title(self, run: Run, data: dict) -> None:
        """
        更新 Session 标题（Agent 生成简短标题时触发）。

        data 预期字段：
          title : str
        """
        from app.models.session import Session as SessionModel

        title: str = str(data.get("title", ""))[:200]
        session: SessionModel | None = self._db.get(SessionModel, run.session_id)
        if session is not None:
            session.title = title
            self._db.flush()

        import asyncio
        asyncio.create_task(
            self._sse.publish(run.session_id, "session_title", data)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text_preview(role: str, content: list) -> str:
    """
    从 PrismMessage content blocks 生成 text_preview（前 200 字）。
    遵守 DOC-01 v4 §4.2 messages 表规则。
    """
    if not content:
        return "[empty]"

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            text = block.get("text", "")
            return text[:200] if text else "[empty]"
        elif btype == "tool_use":
            name = block.get("name", "")
            return f"[tool_use:{name}]"
        elif btype == "tool_result":
            # tool_use_id を含む tool_result block
            inner = block.get("content", [])
            if isinstance(inner, list) and inner:
                first = inner[0]
                if isinstance(first, dict) and first.get("type") == "text":
                    text = first.get("text", "")
                    return f"[tool_result] {text[:190]}"
            return "[tool_result]"

    return "[empty]"
