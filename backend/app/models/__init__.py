"""
Prism v2 — ORM models package

Imports all 19 table models so that:
  1. ``from app.models import *`` works for application code.
  2. Alembic can discover all metadata via ``Base.metadata`` after this
     package is imported in ``alembic/env.py``.

Table count verification (DOC-01 v4 §4.2):
  用户域        (2): users, invite_codes
  会话域        (2): sessions, session_queue_items
  执行域        (4): runs, messages, tool_executions, coordinator_plans *
  模型/Provider (1): providers
  MCP 域        (2): mcp_servers, user_mcp_installs
  IM 域         (3): im_bindings, im_channel_configs, im_message_dedup *
  审计域        (1): audit_logs
  插件/Skill    (1): skill_installs *
  执行恢复      (1): permission_requests *
  Memory        (1): user_memories *
  Total        19    (* = v4 新增)
"""

from app.models.base import Base  # noqa: F401 — ensures Base is importable

# --- 用户域 (2) ---
from app.models.user import InviteCode, User  # noqa: F401

# --- 会话域 (2) ---
from app.models.session import Session, SessionQueueItem  # noqa: F401

# --- 执行域 (4) ---
from app.models.run import Run  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.tool_execution import ToolExecution  # noqa: F401
from app.models.coordinator_plan import CoordinatorPlan  # noqa: F401  # v4 新增

# --- 模型 & Provider 域 (1) ---
from app.models.provider import Provider  # noqa: F401

# --- MCP 域 (2) ---
from app.models.mcp_server import McpServer, UserMcpInstall  # noqa: F401

# --- IM 域 (3) ---
from app.models.im import ImBinding, ImChannelConfig  # noqa: F401
from app.models.im_dedup import ImMessageDedup  # noqa: F401  # v4 新增

# --- 审计域 (1) ---
from app.models.audit import AuditLog  # noqa: F401

# --- 插件 & Skill 域 (1) ---
from app.models.skill_install import SkillInstall  # noqa: F401  # v4 新增

# --- 执行恢复域 (1) ---
from app.models.permission_request import PermissionRequest  # noqa: F401  # v4 新增

# --- Memory 域 (1) ---
from app.models.user_memory import UserMemory  # noqa: F401  # v4 新增

__all__ = [
    "Base",
    # 用户域
    "User",
    "InviteCode",
    # 会话域
    "Session",
    "SessionQueueItem",
    # 执行域
    "Run",
    "Message",
    "ToolExecution",
    "CoordinatorPlan",
    # Provider
    "Provider",
    # MCP
    "McpServer",
    "UserMcpInstall",
    # IM
    "ImBinding",
    "ImChannelConfig",
    "ImMessageDedup",
    # 审计
    "AuditLog",
    # Skill
    "SkillInstall",
    # 执行恢复
    "PermissionRequest",
    # Memory
    "UserMemory",
]
