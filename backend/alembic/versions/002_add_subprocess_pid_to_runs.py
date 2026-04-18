"""Add subprocess_pid to runs table (DOC-07 Task 7.2)

Revision ID: 002
Revises: 001
Create Date: 2026-04-19

Purpose:
  Add `subprocess_pid` INTEGER column to `runs` table.
  Required by DOC-07 Task 7.2 cancel 三模式（ADR-062）：
  Backend needs to SIGTERM/SIGKILL the executor subprocess by PID.
  Field is NULL before launch or after process exits.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("subprocess_pid", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "subprocess_pid")
