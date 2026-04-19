"""Add decision column to permission_requests table

Revision ID: 003_add_decision_to_permission_requests
Revises: 002
Create Date: 2026-04-19

ADR-064: permission-answer 端点需要在 permission_requests 表持久化用户决策。
新增 decision VARCHAR(10) NULLABLE 列，取值 'allow' | 'deny' | NULL（pending 状态）。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "permission_requests",
        sa.Column("decision", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("permission_requests", "decision")
