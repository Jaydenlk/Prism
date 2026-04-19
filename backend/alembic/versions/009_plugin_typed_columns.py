"""Add plugin_type + permissions_json columns to plugins_library

Revision ID: 009
Revises: 008
Create Date: 2026-04-20

DOC-SK R2+R5 / ADR-087 — Typed Plugin Manifest + Permissions.

Changes:
  - ADD COLUMN plugins_library.plugin_type (varchar(30), NOT NULL, default 'tool')
    Enum values: tool | agent_strategy | extension | trigger.
    server_default='tool' is retained so existing rows are backfilled on upgrade
    and future INSERTs without an explicit value still succeed. Application
    code defaults explicitly as well (Pydantic schema + ORM default=).
  - ADD COLUMN plugins_library.permissions_json (jsonb, NOT NULL, default {})
    Stores {allowed_tools, allowed_models, storage_scope, network_access, ...}
    per spec §5.2. server_default='{}' keeps existing rows valid on upgrade.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plugins_library",
        sa.Column(
            "plugin_type",
            sa.String(length=30),
            nullable=False,
            server_default="tool",
        ),
    )
    op.add_column(
        "plugins_library",
        sa.Column(
            "permissions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("plugins_library", "permissions_json")
    op.drop_column("plugins_library", "plugin_type")
