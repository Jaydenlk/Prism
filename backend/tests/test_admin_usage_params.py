"""Tests for GET /admin/usage — group_by/start_date/end_date params are respected."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def usage_client():
    from app.models.base import Base
    from app.models.run import Run
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.session import Session as SessionModel
    from app.main import app
    from app.core.database import get_db
    from app.core.dependencies import get_current_user, require_admin

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_fk(conn, _record):
        conn.execute("PRAGMA foreign_keys=OFF")

    tables = [User.__table__, Provider.__table__, SessionModel.__table__, Run.__table__]
    Base.metadata.create_all(engine, tables=tables)

    Session = sessionmaker(bind=engine)
    db = Session()

    admin = User(
        id=str(uuid.uuid4()),
        email="admin@test.local",
        username="admin",
        password_hash="x",
        role="admin",
    )
    db.add(admin)
    db.commit()

    def _override_get_db():
        yield db

    def _override_current_user():
        return admin

    def _override_require_admin():
        return admin

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_admin] = _override_require_admin

    yield TestClient(app), db, admin

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)
    db.close()
    Base.metadata.drop_all(engine, tables=tables)
    engine.dispose()


def test_admin_usage_default_params(usage_client):
    """No params → 200 with expected shape."""
    client, db, admin = usage_client
    res = client.get("/api/v1/admin/usage")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "total_runs" in data
    assert "per_provider" in data
    assert "daily_trend_30d" in data


def test_admin_usage_group_by_reflected(usage_client):
    """group_by param is accepted and reflected in response."""
    client, db, admin = usage_client
    res = client.get("/api/v1/admin/usage", params={"group_by": "provider"})
    assert res.status_code == 200
    assert res.json()["data"]["group_by"] == "provider"


def test_admin_usage_date_range_filters(usage_client):
    """start_date/end_date filter runs — old run outside range excluded from totals."""
    from app.models.run import Run
    from app.models.session import Session as SessionModel

    client, db, admin = usage_client
    now = datetime.now(timezone.utc)

    sess = SessionModel(
        id=str(uuid.uuid4()),
        user_id=admin.id,
        title="test",
    )
    db.add(sess)
    db.flush()

    old_run = Run(
        id=str(uuid.uuid4()),
        session_id=sess.id,
        user_id=admin.id,
        prompt="test",
        model="claude-3-sonnet",
        status="completed",
        input_tokens=999,
        output_tokens=0,
        created_at=now - timedelta(days=60),
    )
    db.add(old_run)
    db.commit()

    # Query only last 7 days — old_run is 60 days ago, must be excluded
    start = (now - timedelta(days=7)).isoformat()
    end = now.isoformat()
    res = client.get("/api/v1/admin/usage", params={"start_date": start, "end_date": end})
    assert res.status_code == 200
    assert res.json()["data"]["total_runs"] == 0
