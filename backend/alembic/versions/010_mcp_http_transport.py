"""mcp_http_transport: add transport/url/headers_encrypted to mcp_servers.

Revision ID: 010_mcp_http
Revises: 009
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa


revision = "010_mcp_http"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_servers",
        sa.Column("transport", sa.String(20), nullable=False, server_default="stdio"),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("url", sa.Text(), nullable=True),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("headers_encrypted", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("mcp_servers", "headers_encrypted")
    op.drop_column("mcp_servers", "url")
    op.drop_column("mcp_servers", "transport")
