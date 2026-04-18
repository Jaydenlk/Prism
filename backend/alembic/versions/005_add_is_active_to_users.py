"""Add is_active column to users table

Revision ID: 005_add_is_active_to_users
Revises: 004_add_user_id_to_mcp_servers
Create Date: 2026-04-19

DOC-09 Task 9.3: Admin soft-disable users (ADR-083).
Adds is_active BOOLEAN NOT NULL DEFAULT TRUE to the users table so that
DELETE /admin/users/{id} can soft-disable a user without removing the row.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_is_active_to_users"
down_revision: str = "004_add_user_id_to_mcp_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
