"""
pytest conftest — add backend/ to sys.path so that `import app.*` works
without Docker or a full Prism installation.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, JSON
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# Ensure the `backend` directory is on the Python path so that
# `from app.services.im_feishu import FeishuAdapter` resolves correctly.
_BACKEND_DIR = Path(__file__).parent.parent  # .../PrismV3/backend
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# Compile JSONB as TEXT on SQLite (no native JSONB support)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db():
    """In-memory SQLite session for unit tests that need DB access.

    Only creates the tables needed by bootstrap tests (marketplace_registry,
    mcp_servers). JSONB compiles as TEXT; FK checks are disabled so tests
    don't need full users table wiring.
    """
    from app.models.marketplace import MarketplaceRegistry
    from app.models.mcp_server import McpServer, UserMcpInstall
    from app.models.base import Base
    from sqlalchemy import MetaData

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Disable FK enforcement so bootstrap tests don't need a real users row
    @event.listens_for(engine, "connect")
    def _set_fk_pragma(conn, _record):
        conn.execute("PRAGMA foreign_keys=OFF")

    # Only create the tables relevant to our tests
    tables = [
        MarketplaceRegistry.__table__,
        McpServer.__table__,
        UserMcpInstall.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()
