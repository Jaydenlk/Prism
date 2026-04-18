"""
Prism v2 — Run 响应 Schema (DOC-07 Task 7.2)

RunResponse       — GET /runs/{id} 响应体，含 harness_summary JSONB
RunListResponse   — GET /sessions/{id}/runs 列表精简版
CancelRunRequest  — POST /runs/{id}/cancel 请求体（三模式）
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RunResponse(BaseModel):
    """
    Run 详情响应。

    harness_summary JSONB schema 约定见 DOC-07 前置定义。
    status 取值: pending | running | completed | failed | cancelled | timeout
    """

    id: str
    session_id: str
    prompt: str
    status: str
    model: str
    provider_id: str | None
    schedule_mode: str
    agent_type: str | None
    error_message: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    turn_count: int | None
    harness_summary: dict | None  # JSONB，schema 见文档前置定义
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class RunListResponse(BaseModel):
    """Run 列表精简版"""

    id: str
    status: str
    prompt: str
    agent_type: str | None
    turn_count: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class CancelRunRequest(BaseModel):
    """
    取消 Run 请求体 (v4 ADR-062 三模式)。

    mode:
      - "graceful"          (默认) SIGTERM，子进程完成当前 tool 后 break
      - "force"             SIGKILL，立即终止
      - "also_cancel_queue" graceful 当前 + 取消所有后续队列 item
    """

    mode: str = Field(
        default="graceful",
        pattern="^(graceful|force|also_cancel_queue)$",
        description="取消模式: graceful | force | also_cancel_queue",
    )
