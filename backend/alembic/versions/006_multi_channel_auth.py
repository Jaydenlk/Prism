"""Add multi-channel auth columns to users + auth_config table

Revision ID: 006
Revises: 005
Create Date: 2026-04-19

Multi-channel Auth Design (docs/superpowers/specs/2026-04-19-multi-channel-auth-design.md §2.3)

Changes:
  - users: ADD phone, phone_verified, google_id, email_verified
  - CREATE TABLE auth_config (key PK, value_json JSONB, updated_at, updated_by FK)
  - Bootstrap 3 auth_config rows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: new columns -------------------------------------------
    op.add_column(
        "users",
        sa.Column("phone", sa.String(20), unique=True, nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("google_id", sa.String(255), unique=True, nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- auth_config table -------------------------------------------
    op.create_table(
        "auth_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # --- Bootstrap rows -----------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO auth_config (key, value_json) VALUES
              ('allow_oauth_signup_without_invite', 'false'),
              ('allow_phone_registration',           'true'),
              ('require_email_verification',         'false')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("auth_config")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "google_id")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
