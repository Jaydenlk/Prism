"""Add marketplace_registry table + skill_installs.marketplace_id FK

Revision ID: 008
Revises: 007
Create Date: 2026-04-20

DOC-SK R1 / ADR-086 — Skills Marketplace.

Changes:
  - CREATE TABLE marketplace_registry (stores registered Claude Code-format
    marketplaces; catalog_json caches the fetched `.claude-plugin/marketplace.json`)
  - ALTER TABLE skill_installs ADD COLUMN marketplace_id (nullable FK to
    marketplace_registry.id, ON DELETE SET NULL) — links an installed skill
    back to the marketplace it came from when source='marketplace'.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "catalog_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.add_column(
        "skill_installs",
        sa.Column(
            "marketplace_id",
            sa.String(36),
            sa.ForeignKey(
                "marketplace_registry.id",
                name="fk_skill_installs_marketplace_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_skill_installs_marketplace_id",
        "skill_installs",
        type_="foreignkey",
    )
    op.drop_column("skill_installs", "marketplace_id")
    op.drop_table("marketplace_registry")
