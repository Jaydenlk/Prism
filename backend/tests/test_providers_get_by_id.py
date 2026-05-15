"""Tests for GET /api/v1/providers/{provider_id}."""
from __future__ import annotations

import sys
import uuid
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
def provider_db():
    from app.models.base import Base
    from app.models.provider import Provider
    from app.models.user import User

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_fk(conn, _record):
        conn.execute("PRAGMA foreign_keys=OFF")

    tables = [User.__table__, Provider.__table__]
    Base.metadata.create_all(engine, tables=tables)

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()


@pytest.fixture()
def provider_client(provider_db):
    from app.main import app
    from app.core.database import get_db
    from app.core.dependencies import get_current_user
    from app.models.user import User

    owner = User(
        id=str(uuid.uuid4()),
        email="owner@test.local",
        username="owner",
        password_hash="x",
        role="user",
    )
    provider_db.add(owner)
    provider_db.commit()

    def _override_get_db():
        yield provider_db

    def _override_current_user():
        return owner

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    yield TestClient(app), provider_db, owner
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_provider_404(provider_client):
    client, db, owner = provider_client
    res = client.get(f"/api/v1/providers/{uuid.uuid4()}")
    assert res.status_code == 404


def test_get_provider_200(provider_client):
    from app.models.provider import Provider
    from app.core.security import encrypt_value
    from app.core.config import settings

    client, db, owner = provider_client
    encrypted = encrypt_value("sk-test", settings.ENCRYPTION_KEY)
    p = Provider(
        id=str(uuid.uuid4()),
        scope="user",
        user_id=owner.id,
        name="TestProvider",
        protocol="anthropic",
        base_url="https://api.anthropic.com",
        api_key_encrypted=encrypted,
        model_id="claude-3-sonnet",
        config={"capabilities": {"chat": True}},
    )
    db.add(p)
    db.commit()

    res = client.get(f"/api/v1/providers/{p.id}")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["id"] == p.id
    assert data["name"] == "TestProvider"
