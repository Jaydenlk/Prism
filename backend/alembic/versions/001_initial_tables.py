"""Initial 19-table schema for Prism v2

Revision ID: 001
Revises:
Create Date: 2026-04-18 00:00:00.000000

Implements DOC-01 v4 §4.2 — all 19 tables, indexes, and constraints.
Hand-written per DOC-02 Task 2.1 Part B Step 6 (autogenerate forbidden).

Tables created (in FK dependency order):
  用户域:     users, invite_codes
  Provider:   providers
  MCP:        mcp_servers
  IM configs: im_channel_configs
  会话域:     sessions, session_queue_items
  执行域:     runs, messages, tool_executions
              coordinator_plans, permission_requests
  MCP link:   user_mcp_installs
  IM:         im_bindings, im_message_dedup
  审计:       audit_logs
  Skill:      skill_installs
  Memory:     user_memories
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    # ------------------------------------------------------------------
    # 2. invite_codes
    # ------------------------------------------------------------------
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_invite_codes_code"),
    )

    # ------------------------------------------------------------------
    # 3. providers  (must precede sessions which reference runs which reference providers)
    # ------------------------------------------------------------------
    op.create_table(
        "providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="user"),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_healthy", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(scope = 'system' AND user_id IS NULL) OR "
            "(scope = 'user' AND user_id IS NOT NULL)",
            name="ck_providers_scope_user_id",
        ),
    )
    op.create_index(
        "ix_providers_scope_user_default",
        "providers",
        ["scope", "user_id", "is_default"],
    )
    op.create_index(
        "ix_providers_scope_user_priority",
        "providers",
        ["scope", "user_id", "priority"],
    )

    # ------------------------------------------------------------------
    # 4. mcp_servers
    # ------------------------------------------------------------------
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="system"),
        sa.Column("command", sa.String(500), nullable=False),
        sa.Column(
            "args",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "env",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 5. im_channel_configs
    # ------------------------------------------------------------------
    op.create_table(
        "im_channel_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("channel", name="uq_im_channel_configs_channel"),
    )

    # ------------------------------------------------------------------
    # 6. sessions  (blocking_run_id → runs.id added as ALTER TABLE below)
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="idle"),
        # blocking_run_id added via ALTER after runs table is created
        sa.Column("blocking_run_id", sa.String(36), nullable=True),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_pinned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("im_channel", sa.String(50), nullable=True),
        sa.Column("im_chat_id", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sessions_user_updated", "sessions", ["user_id", "updated_at"]
    )
    op.create_index(
        "ix_sessions_user_pinned_updated",
        "sessions",
        ["user_id", "is_pinned", "updated_at"],
    )

    # ------------------------------------------------------------------
    # 7. session_queue_items
    # ------------------------------------------------------------------
    op.create_table(
        "session_queue_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_session_queue_items_session_status_seq",
        "session_queue_items",
        ["session_id", "status", "sequence_no"],
    )

    # ------------------------------------------------------------------
    # 8. runs
    # ------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column(
            "provider_id",
            sa.String(36),
            sa.ForeignKey("providers.id"),
            nullable=True,
        ),
        sa.Column(
            "schedule_mode", sa.String(20), nullable=False, server_default="immediate"
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cache_hit_tokens", sa.Integer, nullable=True),
        sa.Column("cache_miss_tokens", sa.Integer, nullable=True),
        sa.Column("cache_creation_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("turn_count", sa.Integer, nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=True),
        sa.Column(
            "run_mode", sa.String(20), nullable=False, server_default="foreground"
        ),
        sa.Column(
            "parent_run_id",
            sa.String(36),
            sa.ForeignKey("runs.id"),
            nullable=True,
        ),
        sa.Column("harness_version", sa.String(20), nullable=True),
        sa.Column(
            "harness_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_runs_session_created", "runs", ["session_id", "created_at"])
    op.create_index("ix_runs_user_created", "runs", ["user_id", "created_at"])
    op.create_index(
        "ix_runs_status_pending",
        "runs",
        ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ------------------------------------------------------------------
    # 8b. Add sessions.blocking_run_id FK now that runs table exists
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_sessions_blocking_run_id",
        "sessions",
        "runs",
        ["blocking_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # 9. messages
    # ------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("text_preview", sa.String(500), nullable=True),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("is_skill_context", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("skill_name", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_messages_session_seq", "messages", ["session_id", "sequence_no"])
    op.create_index("ix_messages_run_id", "messages", ["run_id"])

    # ------------------------------------------------------------------
    # 10. tool_executions
    # ------------------------------------------------------------------
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column(
            "input", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "output", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("is_error", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("permission_decision", sa.String(20), nullable=True),
        sa.Column("hook_modified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 11. coordinator_plans  (v4 新增)
    # ------------------------------------------------------------------
    op.create_table(
        "coordinator_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "current_step_index", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "step_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_coordinator_plans_run_id", "coordinator_plans", ["run_id"]
    )
    op.create_index(
        "ix_coordinator_plans_status_updated",
        "coordinator_plans",
        ["status", "updated_at"],
    )

    # ------------------------------------------------------------------
    # 12. permission_requests  (v4 新增)
    # ------------------------------------------------------------------
    op.create_table(
        "permission_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column(
            "tool_input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_permission_requests_request_id"),
    )
    op.create_index(
        "ix_permission_requests_run_status",
        "permission_requests",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_permission_requests_status_timeout",
        "permission_requests",
        ["status", "timeout_at"],
    )

    # ------------------------------------------------------------------
    # 13. user_mcp_installs
    # ------------------------------------------------------------------
    op.create_table(
        "user_mcp_installs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mcp_server_id",
            sa.String(36),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "config_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "mcp_server_id", name="uq_user_mcp_installs"
        ),
    )

    # ------------------------------------------------------------------
    # 14. im_bindings
    # ------------------------------------------------------------------
    op.create_table(
        "im_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("platform_user_id", sa.String(200), nullable=False),
        sa.Column(
            "platform_chat_id", sa.String(200), nullable=False, server_default=""
        ),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("pairing_code", sa.String(10), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "channel",
            "platform_user_id",
            "platform_chat_id",
            name="uq_im_bindings_channel_user_chat",
        ),
    )

    # ------------------------------------------------------------------
    # 15. im_message_dedup  (v4 新增)
    # ------------------------------------------------------------------
    op.create_table(
        "im_message_dedup",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("platform_message_id", sa.String(200), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "channel",
            "platform_message_id",
            name="uq_im_message_dedup_channel_msg",
        ),
    )
    op.create_index(
        "ix_im_message_dedup_received_at", "im_message_dedup", ["received_at"]
    )

    # ------------------------------------------------------------------
    # 16. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_audit_logs_action_created", "audit_logs", ["action", "created_at"]
    )

    # ------------------------------------------------------------------
    # 17. skill_installs  (v4 新增)
    # ------------------------------------------------------------------
    op.create_table(
        "skill_installs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.UniqueConstraint(
            "user_id", "skill_name", name="uq_skill_installs_user_skill"
        ),
    )
    op.create_index(
        "ix_skill_installs_user_installed",
        "skill_installs",
        ["user_id", "installed_at"],
    )

    # ------------------------------------------------------------------
    # 18. user_memories  (v4 新增)
    # ------------------------------------------------------------------
    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("memory_text", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(20), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_user_memories_user_id"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("user_memories")
    op.drop_table("skill_installs")
    op.drop_table("audit_logs")
    op.drop_table("im_message_dedup")
    op.drop_table("im_bindings")
    op.drop_table("user_mcp_installs")
    op.drop_table("permission_requests")
    op.drop_table("coordinator_plans")
    op.drop_table("tool_executions")
    op.drop_table("messages")
    # Remove blocking_run_id FK before dropping runs
    op.drop_constraint("fk_sessions_blocking_run_id", "sessions", type_="foreignkey")
    op.drop_table("runs")
    op.drop_table("session_queue_items")
    op.drop_table("sessions")
    op.drop_table("im_channel_configs")
    op.drop_table("mcp_servers")
    op.drop_table("providers")
    op.drop_table("invite_codes")
    op.drop_table("users")
