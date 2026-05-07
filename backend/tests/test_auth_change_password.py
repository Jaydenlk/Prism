"""Tests for POST /auth/change-password (P0-4 audit fix)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password


def _make_user(db, email: str, password: str) -> str:
    from app.models.user import User
    user = User(
        email=email,
        username=f"u{uuid.uuid4().hex[:8]}",
        password_hash=hash_password(password),
        role="user",
    )
    db.add(user)
    db.commit()
    return user.id


def _login_token(client: TestClient, email: str, password: str) -> str:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["access_token"]


def test_change_password_unauthenticated_returns_401(client: TestClient):
    res = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "newpassword"},
    )
    assert res.status_code == 401


def test_change_password_wrong_current_returns_400(client: TestClient, db):
    _make_user(db, "wrong-cp@example.com", "OldPassword!1")
    token = _login_token(client, "wrong-cp@example.com", "OldPassword!1")
    res = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "WRONG", "new_password": "NewPassword!2"},
    )
    assert res.status_code == 400
    assert "当前密码" in res.json()["detail"]


def test_change_password_short_new_returns_422(client: TestClient, db):
    _make_user(db, "short-cp@example.com", "OldPassword!1")
    token = _login_token(client, "short-cp@example.com", "OldPassword!1")
    res = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "OldPassword!1", "new_password": "abc"},
    )
    assert res.status_code == 422


def test_change_password_happy_path_persists(client: TestClient, db):
    _make_user(db, "happy-cp@example.com", "OldPassword!1")
    token = _login_token(client, "happy-cp@example.com", "OldPassword!1")
    res = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "OldPassword!1", "new_password": "NewPassword!2"},
    )
    assert res.status_code == 200

    # New password works for fresh login
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "happy-cp@example.com", "password": "NewPassword!2"},
    )
    assert new_login.status_code == 200

    # Old password rejected
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "happy-cp@example.com", "password": "OldPassword!1"},
    )
    assert old_login.status_code == 401
