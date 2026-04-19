"""Add plugins_library table for user-owned plugin manifests (Task A-3)

Revision ID: 007
Revises: 006
Create Date: 2026-04-19

Changes:
  - CREATE TABLE plugins_library (user-scoped plugin manifest storage)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugins_library",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(50), nullable=False, server_default="1.0.0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("manifest_yaml", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "manifest_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Unique constraint: one plugin name per user
    op.create_unique_constraint(
        "uq_plugins_library_user_name",
        "plugins_library",
        ["user_id", "name"],
    )

    # Index for efficient listing by user
    op.create_index(
        "ix_plugins_library_user_created",
        "plugins_library",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_plugins_library_user_created", table_name="plugins_library")
    op.drop_constraint(
        "uq_plugins_library_user_name", "plugins_library", type_="unique"
    )
    op.drop_table("plugins_library")
