"""
Prism v2 — Task 提交 Schema (DOC-07 Task 7.2)

SubmitTaskRequest  — POST /tasks 请求体
SubmitTaskResponse — 202 响应体，含 accepted_type / queue_position
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SubmitTaskRequest(BaseModel):
    """
    提交任务请求。

    session_id 为 None 时自动创建新 Session。
    agent_type 为 None 时由 TaskRouter 自动路由。
    """

    session_id: str | None = None
    prompt: str = Field(..., min_length=1, description="用户输入内容")
    agent_type: str | None = None  # 显式指定 Agent 类型（None = 自动路由）


class SubmitTaskResponse(BaseModel):
    """
    任务提交响应。

    accepted_type:
      - "immediate"     — session 空闲，立即创建 Run 并启动子进程
      - "queued_query"  — session 繁忙，已加入队列
    """

    session_id: str
    run_id: str | None  # 排队时为 None
    accepted_type: str  # "immediate" | "queued_query"
    queue_position: int | None  # 排队时的队列位置（sequence_no）
