"""Tests for /api/v1/internal/users/{uid}/installed-skills + mcp-servers."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.mcp_server import McpServer
from app.models.skill_install import SkillInstall


def test_installed_skills_unauthorized_without_secret(client: TestClient):
    res = client.get("/api/v1/internal/users/some-uid/installed-skills")
    # FastAPI Header(...) with no default = 422 if header missing
    assert res.status_code in (403, 422)


def test_installed_skills_wrong_secret_returns_403(client: TestClient):
    res = client.get(
        "/api/v1/internal/users/some-uid/installed-skills",
        headers={"X-Callback-Secret": "wrong"},
    )
    assert res.status_code == 403


def test_installed_skills_unknown_user_returns_empty_list(client: TestClient, callback_secret: str):
    res = client.get(
        "/api/v1/internal/users/00000000-0000-0000-0000-000000000000/installed-skills",
        headers={"X-Callback-Secret": callback_secret},
    )
    assert res.status_code == 200
    assert res.json() == {"skills": []}


@pytest.mark.skipif(
    not hasattr(SkillInstall, "status"),
    reason="Task 4 schema (SkillInstall.status / install_path) not yet merged",
)
def test_installed_skills_returns_user_skills(
    client: TestClient, callback_secret: str, seeded_user_with_skill
):
    user_id, skill_name = seeded_user_with_skill
    res = client.get(
        f"/api/v1/internal/users/{user_id}/installed-skills",
        headers={"X-Callback-Secret": callback_secret},
    )
    assert res.status_code == 200
    skills = res.json()["skills"]
    assert any(s["skill_name"] == skill_name for s in skills)
    s = next(s for s in skills if s["skill_name"] == skill_name)
    assert "install_path" in s
    assert "source" in s


def test_mcp_servers_returns_user_scoped_plus_system(
    client: TestClient, callback_secret: str, seeded_user_with_mcp
):
    user_id = seeded_user_with_mcp
    res = client.get(
        f"/api/v1/internal/users/{user_id}/mcp-servers",
        headers={"X-Callback-Secret": callback_secret},
    )
    assert res.status_code == 200
    servers = res.json()["servers"]
    assert all("transport" in s for s in servers)


@pytest.mark.skipif(
    not hasattr(McpServer, "transport"),
    reason="Task 4 schema (McpServer.transport/url/headers_encrypted) not yet merged",
)
def test_mcp_servers_decrypts_http_headers(
    client: TestClient, callback_secret: str, seeded_user_with_http_mcp
):
    user_id = seeded_user_with_http_mcp
    res = client.get(
        f"/api/v1/internal/users/{user_id}/mcp-servers",
        headers={"X-Callback-Secret": callback_secret},
    )
    assert res.status_code == 200
    http_server = next(
        s for s in res.json()["servers"] if s["transport"] == "http"
    )
    # Plaintext headers in response (executor consumes plaintext)
    assert "headers" in http_server
    assert http_server["headers"].get("Authorization", "").startswith("Bearer ")
