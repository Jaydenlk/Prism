"""
pytest conftest — add backend/ to sys.path so that `import app.*` works
without Docker or a full Prism installation.
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# Ensure the `backend` directory is on the Python path so that
# `from app.services.im_feishu import FeishuAdapter` resolves correctly.
_BACKEND_DIR = Path(__file__).parent.parent  # .../PrismV3/backend
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ---------------------------------------------------------------------------
# Set required secrets before any app.core.config import
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Inject test secrets before pydantic-settings validates them."""
    os.environ.setdefault(
        "JWT_SECRET",
        "test_jwt_secret_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    os.environ.setdefault(
        "ENCRYPTION_KEY",
        "a" * 64,  # 64 hex chars = 32 bytes, valid AES-256-GCM key
    )
    os.environ.setdefault(
        "CALLBACK_SECRET",
        "test_callback_secret_ccccccccccccccccccccccccccccccccccccccccccccccc",
    )
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://prism:prism_dev_pass@localhost:5432/prism_test",
    )
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Compile JSONB as TEXT on SQLite (no native JSONB support)
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


# ---------------------------------------------------------------------------
# db fixture — in-memory SQLite session
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """In-memory SQLite session with all tables needed for plugin bootstrap tests."""
    from app.models.base import Base
    from app.models.audit import AuditLog
    from app.models.marketplace import MarketplaceRegistry
    from app.models.mcp_server import McpServer, UserMcpInstall
    from app.models.skill_install import SkillInstall
    from app.models.user import User

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_fk_pragma(conn, _record):
        conn.execute("PRAGMA foreign_keys=OFF")

    tables = [
        MarketplaceRegistry.__table__,
        McpServer.__table__,
        UserMcpInstall.__table__,
        SkillInstall.__table__,
        User.__table__,
        AuditLog.__table__,
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


# ---------------------------------------------------------------------------
# client fixture — TestClient with get_db overridden to use test db
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db):
    """FastAPI TestClient with get_db overridden to use in-memory SQLite."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Secret fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def callback_secret() -> str:
    from app.core.config import settings
    return settings.CALLBACK_SECRET


# ---------------------------------------------------------------------------
# Seeded data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_user_with_skill(db) -> tuple[str, str]:
    from app.models.user import User
    from app.models.skill_install import SkillInstall

    user = User(
        email=f"t1-{uuid.uuid4()}@test.local",
        username=f"t1user{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role="user",
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)
    si = SkillInstall(
        user_id=user.id,
        skill_name="test-skill",
        source="local",
        source_url=None,
        version="1.0",
        installed_at=now,
        updated_at=now,
        metadata_={"install_path": "/tmp/test", "status": "installed"},
    )
    db.add(si)
    db.commit()
    return user.id, "test-skill"


@pytest.fixture()
def seeded_user_with_mcp(db) -> str:
    from app.models.user import User
    from app.models.mcp_server import McpServer, UserMcpInstall

    user = User(
        email=f"t2-{uuid.uuid4()}@test.local",
        username=f"t2user{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role="user",
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)
    server = McpServer(
        name="test-stdio",
        scope="user",
        user_id=user.id,
        command="echo",
        args=["hi"],
        env={},
        created_at=now,
    )
    db.add(server)
    db.flush()

    install = UserMcpInstall(
        user_id=user.id,
        mcp_server_id=server.id,
        is_enabled=True,
        created_at=now,
    )
    db.add(install)
    db.commit()
    return user.id


@pytest.fixture()
def seeded_user_with_http_mcp(db) -> str:
    import json
    from app.models.user import User
    from app.models.mcp_server import McpServer, UserMcpInstall
    from app.core.security import encrypt_value
    from app.core.config import settings

    user = User(
        email=f"t3-{uuid.uuid4()}@test.local",
        username=f"t3user{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role="user",
    )
    db.add(user)
    db.flush()

    headers = {"Authorization": "Bearer token-abc", "Content-Type": "application/json"}
    encrypted = encrypt_value(json.dumps(headers), settings.ENCRYPTION_KEY)

    now = datetime.now(timezone.utc)
    server = McpServer(
        name="test-http",
        scope="user",
        user_id=user.id,
        command="__http__",
        args=[],
        env={},
        transport="http",
        url="https://example.test/mcp",
        headers_encrypted=encrypted,
        created_at=now,
    )
    db.add(server)
    db.flush()

    install = UserMcpInstall(
        user_id=user.id,
        mcp_server_id=server.id,
        is_enabled=True,
        created_at=now,
    )
    db.add(install)
    db.commit()
    return user.id
