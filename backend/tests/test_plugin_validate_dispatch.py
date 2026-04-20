"""
Session 4a — /plugins/validate-manifest dispatch by type (ADR-087 偏离点 #2+#3).

Runs in-container against a live uvicorn on localhost:8000. The tests hit the
real FastAPI app (no TestClient, no lifespan gymnastics) and admin-authenticate
via the standard /auth/login flow.
"""
from __future__ import annotations

import httpx
import pytest

BASE = "http://localhost:8000/api/v1"


@pytest.fixture(scope="module")
def admin_token() -> str:
    with httpx.Client(timeout=10.0) as c:
        r = c.post(
            f"{BASE}/auth/login",
            json={"email": "admin@prism.dev", "password": "PrismAdmin!2026"},
        )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["data"]["access_token"]


def _post_validate(token: str, manifest: dict) -> httpx.Response:
    with httpx.Client(timeout=10.0) as c:
        return c.post(
            f"{BASE}/plugins/validate-manifest",
            headers={"Authorization": f"Bearer {token}"},
            json={"manifest": manifest},
        )


def test_tool_manifest_valid_passes(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "tool",
        "parameters": {"query": "string"},
        "returns": "string",
    })
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["valid"] is True
    assert body["type"] == "tool"


def test_tool_manifest_missing_name_422(admin_token: str) -> None:
    r = _post_validate(admin_token, {"type": "tool"})
    assert r.status_code == 422, r.text
    detail = r.json().get("detail")
    assert any("name" in str(e).lower() for e in (detail or []))


def test_agent_strategy_missing_reasoning_pattern_422(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "agent_strategy",
        "max_turns": 5,
    })
    assert r.status_code == 422, r.text


def test_extension_unknown_hook_422(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "extension",
        "hook": "not_a_real_hook",
        "middleware_class_path": "app.X",
    })
    assert r.status_code == 422, r.text


def test_trigger_missing_event_source_422(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "trigger",
        "config": {},
    })
    assert r.status_code == 422, r.text


def test_unknown_type_422(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "not_a_type",
    })
    assert r.status_code == 422, r.text
    assert "not_a_type" in r.text


def test_type_defaults_to_tool_when_absent(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "parameters": {},
        "returns": "string",
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["type"] == "tool"


def test_permissions_parsed_into_pydantic(admin_token: str) -> None:
    r = _post_validate(admin_token, {
        "name": "p",
        "version": "1.0.0",
        "type": "tool",
        "parameters": {},
        "returns": "string",
        "permissions": {
            "allowed_tools": ["fetch", "mcp.*"],
            "allowed_models": ["claude-*"],
            "storage_scope": "session",
            "network_access": False,
        },
    })
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["permissions"]["storage_scope"] == "session"
    assert data["permissions"]["network_access"] is False
