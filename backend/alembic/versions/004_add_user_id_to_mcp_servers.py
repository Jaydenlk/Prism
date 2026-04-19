"""Add user_id column to mcp_servers table

Revision ID: 004_add_user_id_to_mcp_servers
Revises: 003_add_decision_to_permission_requests
Create Date: 2026-04-19

DOC-09 Task 9.1: Support user-scoped MCP Servers (scope='user').
Adds nullable user_id FK to users.id so that user-created MCP Servers
can be filtered by owner (铁律 4: data isolation).

scope='system' rows keep user_id=NULL (built-ins are not user-owned).
scope='user'   rows must have user_id set (enforced at service layer).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_mcp_servers_user_id",
        "mcp_servers",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_user_id", table_name="mcp_servers")
    op.drop_column("mcp_servers", "user_id")
