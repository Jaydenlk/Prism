# Plugin Bootstrap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up Skills + MCP runtime so agents actually use installed skills and MCP tools — fix the root cause that `executor/__main__.py` Step 3d skips PluginHost / SkillLoader instantiation, plus add HTTP transport for MCP and integrate exa + Brave + Tavily as builtin search providers.

**Architecture:** Extend backend `internal.py` with 2 endpoints serving executor's plugin bootstrap; add `transport`/`url`/`headers_encrypted` fields to mcp_servers; add HTTP Streamable transport branch in MCPClient (per MCP spec 2025-03-26); insert plugin bootstrap section at executor `__main__.py` Step 3d that fetches user-installed skills/servers via CALLBACK_SECRET HTTP and registers MCP tools to ToolRegistry + assembler.update_tools().

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy + Alembic + httpx (async) + cryptography (AES-256-GCM via `app.core.security.encrypt_value/decrypt_value`) + pytest + Playwright (e2e). MCP HTTP transport per spec 2025-03-26 (Streamable HTTP, SSE response, Mcp-Session-Id stateful).

---

## File Structure (Locked)

| Path | Action | Owner Task | Purpose |
|---|---|---|---|
| `backend/app/api/v1/internal.py` | **EXTEND** (existing file, lines 39+) | Task 1 (W1) | Add 2 GET endpoints for executor plugin bootstrap |
| `backend/app/services/mcp_service.py` | EXTEND | Task 2 (W2) + Task 3 (W3) + Task 6 (W6) | `test_server()` real impl + `_BUILTIN_MCP_SERVERS` add 3 entries |
| `backend/app/api/v1/mcp.py` | MODIFY (lines 108-123 stub) | Task 2 (W2) | Replace test_server stub call wiring |
| `backend/app/services/marketplace_service.py` | EXTEND | Task 3 (W3) | Add `bootstrap_default_marketplace()` |
| `backend/app/main.py` | MODIFY (lifespan) | Task 3 (W3) | Call marketplace bootstrap on startup |
| `backend/app/models/mcp_server.py` | MODIFY | Task 4 (W4) | Add 3 fields: transport / url / headers_encrypted |
| `backend/app/schemas/mcp.py` | MODIFY | Task 4 (W4) | Schema fields + validators + Authorization mask |
| `backend/alembic/versions/010_mcp_http_transport.py` | **NEW** | Task 4 (W4) | Migration adding 3 columns |
| `backend/Dockerfile` | MODIFY | Task 3 (W3) | `apt-get install -y nodejs npm` |
| `executor/plugins/mcp_client.py` | EXTEND | Task 5 (W5) | Add HttpStreamableTransport branch |
| `executor/plugins/host.py` | MODIFY (`_start_mcp_server`) | Task 5 (W5) | Dispatch on transport field |
| `executor/__main__.py` | MODIFY (lines 491-509 Step 3d) | Task 6 (W6) | Insert PluginHost + SkillLoader bootstrap |
| `e2e/tests/plugin-bootstrap-real-call.spec.ts` | **NEW** | Task 7 (W7) | Playwright real-call double-viewport |
| `frontend/admin.html` | MODIFY (MCP servers tab) | Task 4 (W4) | transport radio + url/headers JSON editor |

**Test files (each task creates its own):**
- `backend/tests/test_internal_plugin_endpoints.py` (Task 1)
- `backend/tests/test_mcp_test_server.py` (Task 2)
- `backend/tests/test_marketplace_bootstrap.py` (Task 3)
- `backend/tests/test_mcp_builtin_stdio.py` (Task 3)
- `backend/tests/test_mcp_http_schema.py` (Task 4)
- `executor/tests/test_mcp_client_http.py` (Task 5)
- `executor/tests/test_plugin_host_dispatch.py` (Task 5)
- `executor/tests/test_plugin_bootstrap_main.py` (Task 6)
- `backend/tests/test_mcp_builtin_exa.py` (Task 6)

---

## Execution Batches

| Batch | Tasks (Workers) | Parallel? | Notes |
|---|---|---|---|
| Batch 1 | T1 (W1) + T2 (W2) + T3 (W3) + T4 (W4) | ✅ All parallel — no shared file conflicts | Sonnet x4 dispatched simultaneously |
| Batch 2 | T5 (W5) + T6 (W6) | ✅ Parallel | Both depend on Batch 1 outputs (DB schema + internal endpoints) |
| Batch 3 | T7 (W7) | Solo | qa-engineer drives Playwright real call |

Between batches: main agent integrates handoffs, verifies each Batch 1 task's tests pass before unlocking Batch 2.

---

## Task 1 (W1): L1 — Backend internal endpoints for plugin bootstrap

**Files:**
- Modify: `backend/app/api/v1/internal.py` (extend existing router, lines 39+)
- Create: `backend/tests/test_internal_plugin_endpoints.py`
- Read for context: `backend/app/models/skill_install.py`, `backend/app/models/mcp_server.py`, `backend/app/core/security.py` (decrypt_value)

**Decision context (from spec):**
- HTTP server rows have `headers_encrypted` field (TEXT, AES-256-GCM via `app.core.security.decrypt_value`); endpoint must decrypt → return plaintext to executor
- stdio rows have `command/args/env`; HTTP rows have `transport='http' + url + headers_encrypted`
- CALLBACK_SECRET via `X-Callback-Secret` header, reuse `_verify_callback_secret` Depends already in this file
- After Task 4 lands the schema, this endpoint returns `transport` field too. Task 1 writes the endpoint expecting these fields exist — Task 4 lands the model first via migration, but Task 1 dev can stub via the new `transport` attribute referenced as `getattr(server, 'transport', 'stdio')` to avoid hard dependency on Batch 1 ordering. **NOTE**: Once Task 4 merges, replace `getattr` with direct attribute access.

- [ ] **Step 1: Write failing tests for both endpoints**

Create `backend/tests/test_internal_plugin_endpoints.py`:

```python
"""Tests for /api/v1/internal/users/{uid}/installed-skills + mcp-servers."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
    # Should contain both system-scope (no user_id) and user-scope (matching user_id) installed
    assert all("transport" in s for s in servers)


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
```

The conftest `client`, `callback_secret`, `seeded_user_with_skill`, `seeded_user_with_mcp`, `seeded_user_with_http_mcp` fixtures must be added to `backend/tests/conftest.py` — implementer creates these.

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd .worktrees/plugin-bootstrap/backend && pytest tests/test_internal_plugin_endpoints.py -v
```
Expected: FAIL — endpoints not defined.

- [ ] **Step 3: Implement endpoints in internal.py**

Append to `backend/app/api/v1/internal.py`:

```python
# ---------------------------------------------------------------------------
# GET /internal/users/{user_id}/installed-skills
# ---------------------------------------------------------------------------

from app.models.skill_install import SkillInstall
from app.models.mcp_server import McpServer, UserMcpInstall
from app.core.security import decrypt_value


@router.get(
    "/users/{user_id}/installed-skills",
    include_in_schema=False,
)
async def get_user_installed_skills(
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, list[dict[str, Any]]]:
    """
    Executor 启动期拉取 user-installed skills.

    返回结构: {"skills": [{"skill_name", "install_path", "source", "source_url", "version"}, ...]}
    """
    rows = (
        db.query(SkillInstall)
        .filter(
            SkillInstall.user_id == user_id,
            SkillInstall.status == "installed",
        )
        .all()
    )
    return {
        "skills": [
            {
                "skill_name": r.skill_name,
                "install_path": r.install_path,
                "source": r.source,
                "source_url": r.source_url,
                "version": r.version,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# GET /internal/users/{user_id}/mcp-servers
# ---------------------------------------------------------------------------

@router.get(
    "/users/{user_id}/mcp-servers",
    include_in_schema=False,
)
async def get_user_mcp_servers(
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_callback_secret),
) -> dict[str, list[dict[str, Any]]]:
    """
    Executor 启动期拉取该 user 可用的 MCP servers (system-scope + user-installed user-scope).

    返回结构: {"servers": [{...row..., transport, headers (plaintext if http)}, ...]}
    HTTP 行的 headers_encrypted 在此处解密为 plaintext headers 字典.
    """
    # System-scope: 所有用户共享 (user_id IS NULL)
    system_rows = (
        db.query(McpServer)
        .filter(McpServer.scope == "system", McpServer.user_id.is_(None))
        .all()
    )
    # User-scope: only the servers this user installed
    user_rows = (
        db.query(McpServer)
        .join(UserMcpInstall, UserMcpInstall.mcp_server_id == McpServer.id)
        .filter(
            UserMcpInstall.user_id == user_id,
            UserMcpInstall.is_enabled.is_(True),
        )
        .all()
    )
    all_rows = system_rows + user_rows

    out: list[dict[str, Any]] = []
    for r in all_rows:
        transport = getattr(r, "transport", "stdio")
        d: dict[str, Any] = {
            "id": r.id,
            "name": r.name,
            "scope": r.scope,
            "transport": transport,
            "command": r.command,
            "args": r.args,
            "env": r.env,
        }
        if transport == "http":
            d["url"] = getattr(r, "url", None)
            ciphertext = getattr(r, "headers_encrypted", None)
            if ciphertext:
                plaintext = decrypt_value(ciphertext, settings.ENCRYPTION_KEY)
                import json as _json
                d["headers"] = _json.loads(plaintext)
            else:
                d["headers"] = {}
        out.append(d)
    return {"servers": out}
```

Add fixtures to `backend/tests/conftest.py`:

```python
import pytest
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.skill_install import SkillInstall
from app.models.mcp_server import McpServer, UserMcpInstall
from app.core.security import encrypt_value
import json


@pytest.fixture
def callback_secret() -> str:
    return settings.CALLBACK_SECRET


@pytest.fixture
def seeded_user_with_skill(db: Session) -> tuple[str, str]:
    user = User(email="t1@test.local", password_hash="x", role="user")
    db.add(user); db.flush()
    si = SkillInstall(
        user_id=user.id, skill_name="test-skill", source="local",
        source_url=None, version="1.0", install_path="/tmp/test", status="installed",
    )
    db.add(si); db.commit()
    return user.id, "test-skill"


@pytest.fixture
def seeded_user_with_mcp(db: Session) -> str:
    user = User(email="t2@test.local", password_hash="x", role="user")
    db.add(user); db.flush()
    server = McpServer(
        name="test-stdio", scope="user", user_id=user.id,
        command="echo", args=["hi"], env={},
    )
    db.add(server); db.flush()
    install = UserMcpInstall(user_id=user.id, mcp_server_id=server.id, is_enabled=True)
    db.add(install); db.commit()
    return user.id


@pytest.fixture
def seeded_user_with_http_mcp(db: Session) -> str:
    user = User(email="t3@test.local", password_hash="x", role="user")
    db.add(user); db.flush()
    headers = {"Authorization": "Bearer token-abc", "Content-Type": "application/json"}
    encrypted = encrypt_value(json.dumps(headers), settings.ENCRYPTION_KEY)
    server = McpServer(
        name="test-http", scope="user", user_id=user.id,
        command="__http__", args=[], env={},
        transport="http", url="https://example.test/mcp",
        headers_encrypted=encrypted,
    )
    db.add(server); db.flush()
    install = UserMcpInstall(user_id=user.id, mcp_server_id=server.id, is_enabled=True)
    db.add(install); db.commit()
    return user.id
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd .worktrees/plugin-bootstrap/backend && pytest tests/test_internal_plugin_endpoints.py -v
```
Expected: 6/6 PASS.

> NOTE: `seeded_user_with_http_mcp` requires Task 4 schema. If Task 4 hasn't merged yet, mark this fixture with `@pytest.mark.skip("requires Task 4 schema")` until merged. Document this in handoff.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/internal.py backend/tests/test_internal_plugin_endpoints.py backend/tests/conftest.py
git commit -m "feat(internal): add /users/{uid}/installed-skills + mcp-servers endpoints

Executor bootstrap fetches user-scoped plugins via CALLBACK_SECRET. HTTP MCP
servers decrypt headers_encrypted on response (plaintext to executor; key never
crosses process boundary).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 (W2): L3 — POST /mcp-servers/{id}/test real connection

**Files:**
- Modify: `backend/app/services/mcp_service.py` (replace `test_server` stub at lines 206-232)
- Modify: `backend/app/api/v1/mcp.py` (lines 108-123)
- Create: `backend/tests/test_mcp_test_server.py`
- Read for context: `executor/plugins/mcp_client.py` (existing stdio start)

**Decision context:**
- Replace stub returning `{success: True, tools: ["tools"]}` with real transient MCPClient connection + `list_tools()` + 10s timeout
- Both stdio and http transport branches dispatched (after Task 4 schema lands & Task 5 HTTP branch lands; until then, http transport returns `{success: False, error: "http transport pending"}` graceful)
- Returns `{success: bool, tools: list[str], error: str | None, latency_ms: int}`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_mcp_test_server.py`:

```python
"""Tests for MCPService.test_server real connection."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch

import pytest
from app.services.mcp_service import MCPService


@pytest.mark.asyncio
async def test_test_server_stdio_success(db, monkeypatch):
    """Stdio MCP: subprocess starts → list_tools returns names → success."""
    from app.models.mcp_server import McpServer
    server = McpServer(name="echo-test", scope="system", command="echo", args=["{}"], env={})
    db.add(server); db.commit()

    # Patch MCPClient transient: simulate subprocess + tool list
    fake_client = AsyncMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[{"name": "search"}, {"name": "fetch"}])
    fake_client.stop = AsyncMock(return_value=None)
    with patch("app.services.mcp_service.MCPClient", return_value=fake_client):
        svc = MCPService(db)
        result = await svc.test_server(server.id)

    assert result["success"] is True
    assert set(result["tools"]) == {"search", "fetch"}
    assert result["error"] is None
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_test_server_stdio_timeout(db, monkeypatch):
    """Stdio MCP that hangs → 10s timeout → success=False."""
    from app.models.mcp_server import McpServer
    server = McpServer(name="hang-test", scope="system", command="sleep", args=["100"], env={})
    db.add(server); db.commit()

    async def hang(): import asyncio; await asyncio.sleep(60)
    fake_client = AsyncMock()
    fake_client.start = hang
    fake_client.stop = AsyncMock()
    with patch("app.services.mcp_service.MCPClient", return_value=fake_client):
        svc = MCPService(db)
        result = await svc.test_server(server.id)

    assert result["success"] is False
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_test_server_http_pending(db):
    """HTTP transport returns graceful pending until Task 5 merges."""
    # Skip if schema doesn't have transport field yet
    pytest.importorskip("app.models.mcp_server")
    from app.models.mcp_server import McpServer
    if not hasattr(McpServer, "transport"):
        pytest.skip("Task 4 schema not yet merged")
    server = McpServer(
        name="http-test", scope="system", command="__http__", args=[], env={},
        transport="http", url="https://mcp.example.test/mcp", headers_encrypted=None,
    )
    db.add(server); db.commit()
    svc = MCPService(db)
    result = await svc.test_server(server.id)
    # Until Task 5 lands HTTP branch, return graceful failure
    assert isinstance(result, dict)
    assert "success" in result


@pytest.mark.asyncio
async def test_test_server_unknown_id_returns_404_dict(db):
    svc = MCPService(db)
    result = await svc.test_server("00000000-0000-0000-0000-000000000000")
    assert result["success"] is False
    assert "not found" in result["error"].lower()
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd .worktrees/plugin-bootstrap/backend && pytest tests/test_mcp_test_server.py -v
```
Expected: FAIL — `test_server` returns stub.

- [ ] **Step 3: Implement real test_server**

Replace `mcp_service.test_server()` body (currently stub returning fixed `True`):

```python
async def test_server(self, server_id: str) -> dict[str, Any]:
    """Real connection test: spin up transient MCPClient, list_tools, 10s timeout."""
    import asyncio
    import time
    from executor.plugins.mcp_client import MCPClient

    server = self.db.query(McpServer).filter(McpServer.id == server_id).first()
    if server is None:
        return {"success": False, "tools": [], "error": "Server not found", "latency_ms": 0}

    transport = getattr(server, "transport", "stdio")
    started = time.monotonic()

    if transport == "http":
        # Pre-Task-5: return graceful pending
        # Post-Task-5: instantiate HTTP-mode client and list tools
        try:
            from app.core.security import decrypt_value
            from app.core.config import settings as _settings
            import json as _json
            ciphertext = getattr(server, "headers_encrypted", None)
            headers = _json.loads(decrypt_value(ciphertext, _settings.ENCRYPTION_KEY)) if ciphertext else {}
            client = MCPClient(
                name=server.name,
                transport="http",
                url=getattr(server, "url"),
                headers=headers,
            )
        except (TypeError, AttributeError):
            return {"success": False, "tools": [], "error": "HTTP transport branch not yet available", "latency_ms": 0}
    else:
        client = MCPClient(
            name=server.name,
            transport="stdio",
            command=server.command,
            args=list(server.args or []),
            env=dict(server.env or {}),
        )

    try:
        await asyncio.wait_for(client.start(), timeout=10.0)
        tools = await asyncio.wait_for(client.list_tools(), timeout=5.0)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "success": True,
            "tools": [t.get("name") if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools],
            "error": None,
            "latency_ms": elapsed_ms,
        }
    except asyncio.TimeoutError:
        return {"success": False, "tools": [], "error": "Connection timeout (10s)", "latency_ms": 10_000}
    except Exception as e:
        return {"success": False, "tools": [], "error": f"{type(e).__name__}: {e}", "latency_ms": int((time.monotonic() - started) * 1000)}
    finally:
        try:
            await client.stop()
        except Exception:
            pass
```

Update `mcp.py` test endpoint to call this and return as-is:

```python
@router.post("/mcp-servers/{server_id}/test", status_code=200)
async def test_server_endpoint(
    server_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Real connection test against MCP server."""
    return await MCPService(db).test_server(server_id)
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
pytest tests/test_mcp_test_server.py -v
```
Expected: 4/4 PASS (1 skip if Task 4 schema not yet merged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/mcp_service.py backend/app/api/v1/mcp.py backend/tests/test_mcp_test_server.py
git commit -m "feat(mcp): replace test_server stub with real transient connection

10s timeout, returns {success, tools, error, latency_ms}. Stdio branch fully
working; HTTP branch graceful pending until Task 5 lands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 (W3): L4 + L7 — Default marketplace bootstrap + Brave/Tavily stdio builtins + Dockerfile

**Files:**
- Modify: `backend/app/services/marketplace_service.py` (add bootstrap function)
- Modify: `backend/app/main.py` (lifespan call)
- Modify: `backend/app/services/mcp_service.py` (extend `_BUILTIN_MCP_SERVERS` — Brave + Tavily, NOT exa yet — exa is Task 6 because http transport)
- Modify: `backend/Dockerfile` (apt-get install nodejs npm)
- Create: `backend/tests/test_marketplace_bootstrap.py`
- Create: `backend/tests/test_mcp_builtin_stdio.py`

**Decision context:**
- Default marketplace: `anthropics/claude-plugins-official`, only registered if marketplace_registry table empty at startup
- Brave: `npx -y @modelcontextprotocol/server-brave-search`, env `BRAVE_API_KEY`
- Tavily: `npx -y tavily-mcp@latest`, env `TAVILY_API_KEY`
- env-var-missing → skip registration (graceful, log info)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_marketplace_bootstrap.py`:

```python
"""Tests for marketplace bootstrap on startup."""
from __future__ import annotations
import pytest
from app.services.marketplace_service import MarketplaceService


def test_bootstrap_default_when_empty(db):
    """Empty marketplace_registry → default registered."""
    from app.models.marketplace import MarketplaceRegistry
    db.query(MarketplaceRegistry).delete(); db.commit()
    svc = MarketplaceService(db)
    svc.bootstrap_default_marketplace()
    rows = db.query(MarketplaceRegistry).all()
    assert len(rows) == 1
    assert rows[0].name == "anthropics/claude-plugins-official"


def test_bootstrap_skipped_when_existing(db):
    """Non-empty → skipped (no duplicate)."""
    from app.models.marketplace import MarketplaceRegistry
    db.query(MarketplaceRegistry).delete()
    db.add(MarketplaceRegistry(name="user/custom", url="https://example.test/x"))
    db.commit()
    svc = MarketplaceService(db)
    svc.bootstrap_default_marketplace()
    rows = db.query(MarketplaceRegistry).all()
    assert len(rows) == 1  # still 1, no duplicate added
    assert rows[0].name == "user/custom"
```

Create `backend/tests/test_mcp_builtin_stdio.py`:

```python
"""Tests for Brave + Tavily stdio builtins."""
import os
import pytest
from app.services.mcp_service import MCPService, _BUILTIN_MCP_SERVERS


def test_brave_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "brave-search" in names


def test_tavily_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "tavily" in names


def test_register_skips_brave_if_no_key(db, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="brave-search").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    assert db.query(McpServer).filter_by(name="brave-search").first() is None


def test_register_creates_brave_if_key_set(db, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key-123")
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="brave-search").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    row = db.query(McpServer).filter_by(name="brave-search").first()
    assert row is not None
    assert row.scope == "system"
    assert "BRAVE_API_KEY" in row.env
    assert row.env["BRAVE_API_KEY"] == "test-key-123"
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
pytest tests/test_marketplace_bootstrap.py tests/test_mcp_builtin_stdio.py -v
```
Expected: FAIL — `bootstrap_default_marketplace` doesn't exist; brave/tavily not in builtins.

- [ ] **Step 3: Implement bootstrap_default_marketplace**

Append to `backend/app/services/marketplace_service.py`:

```python
def bootstrap_default_marketplace(self) -> None:
    """
    Register default Anthropic plugin marketplace if registry is empty.
    Idempotent: skips if any marketplace already exists.
    """
    from app.models.marketplace import MarketplaceRegistry
    if self.db.query(MarketplaceRegistry).first() is not None:
        logger.info("marketplace.bootstrap_skipped", reason="non_empty_registry")
        return
    default = MarketplaceRegistry(
        name="anthropics/claude-plugins-official",
        url="https://github.com/anthropics/claude-plugins-official",
    )
    # If model has more fields (description, owner, catalog_json, is_default), set sensible defaults
    if hasattr(default, "description"):
        default.description = "Official Anthropic Claude plugins marketplace (auto-bootstrapped)"
    if hasattr(default, "owner"):
        default.owner = "anthropics"
    if hasattr(default, "catalog_json"):
        default.catalog_json = {"plugins": []}
    if hasattr(default, "is_default"):
        default.is_default = True
    self.db.add(default)
    self.db.commit()
    logger.info("marketplace.bootstrap_default", name=default.name)
```

Modify `backend/app/main.py` lifespan to call it:

```python
# Inside existing FastAPI lifespan @asynccontextmanager
from app.services.marketplace_service import MarketplaceService
from app.core.database import SessionLocal
db = SessionLocal()
try:
    MarketplaceService(db).bootstrap_default_marketplace()
finally:
    db.close()
```

(Place this near the existing `register_builtin_servers` call.)

- [ ] **Step 4: Add Brave + Tavily to _BUILTIN_MCP_SERVERS**

Modify `backend/app/services/mcp_service.py`. The `_BUILTIN_MCP_SERVERS` list already exists (currently 2 entries). Append:

```python
_BUILTIN_MCP_SERVERS = [
    # ... existing entries (web_search, filesystem) ...
    {
        "name": "brave-search",
        "description": "Brave Search MCP — independent web index with 2000 free queries/month.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_var": "BRAVE_API_KEY",  # used by register_builtin_servers
    },
    {
        "name": "tavily",
        "description": "Tavily AI Search MCP — agentic search with 1000 free queries/month.",
        "command": "npx",
        "args": ["-y", "tavily-mcp@latest"],
        "env_var": "TAVILY_API_KEY",
    },
]
```

In `register_builtin_servers()`, gate each entry on its `env_var`:

```python
def register_builtin_servers(self) -> None:
    """Register or refresh _BUILTIN_MCP_SERVERS, skipping entries whose env var is unset."""
    import os
    for spec in _BUILTIN_MCP_SERVERS:
        env_var = spec.get("env_var")
        if env_var:
            api_key = os.environ.get(env_var)
            if not api_key:
                logger.info("mcp.builtin.skipped", name=spec["name"], reason=f"{env_var} not set")
                continue
            env = {env_var: api_key}
        else:
            env = {}
        existing = self.db.query(McpServer).filter_by(name=spec["name"], scope="system").first()
        if existing:
            # update env on key rotation
            existing.env = env
            self.db.commit()
            continue
        row = McpServer(
            name=spec["name"],
            description=spec.get("description"),
            scope="system",
            command=spec["command"],
            args=spec.get("args", []),
            env=env,
        )
        self.db.add(row)
        self.db.commit()
        logger.info("mcp.builtin.registered", name=spec["name"])
```

- [ ] **Step 5: Update Dockerfile**

In `backend/Dockerfile`, after existing apt-get installs (where `git` was added), append `nodejs npm`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*
```

(Adjust to merge with the existing `apt-get install` line — don't add a second one.)

- [ ] **Step 6: Run all tests, verify PASS**

```bash
pytest tests/test_marketplace_bootstrap.py tests/test_mcp_builtin_stdio.py -v
```
Expected: 6/6 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/marketplace_service.py backend/app/main.py backend/app/services/mcp_service.py backend/Dockerfile backend/tests/test_marketplace_bootstrap.py backend/tests/test_mcp_builtin_stdio.py
git commit -m "feat(plugin-bootstrap): default marketplace + brave/tavily stdio builtins

- bootstrap_default_marketplace() auto-registers anthropics/claude-plugins-official
  on startup if registry empty (idempotent)
- _BUILTIN_MCP_SERVERS adds brave-search + tavily; gracefully skip when API key
  env var unset
- Dockerfile installs nodejs+npm for npx-based MCP servers

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 (W4): L5a — MCP HTTP transport DB migration + schema + frontend tab

**Files:**
- Modify: `backend/app/models/mcp_server.py` (add 3 fields)
- Modify: `backend/app/schemas/mcp.py` (schemas + validators + mask)
- Create: `backend/alembic/versions/010_mcp_http_transport.py`
- Modify: `frontend/admin.html` (MCP servers tab — transport radio + url + headers JSON editor)
- Create: `backend/tests/test_mcp_http_schema.py`

**Decision context:**
- `transport` default 'stdio' (back-compat for existing rows)
- `url` nullable (only set when transport='http')
- `headers_encrypted` TEXT nullable (AES-256-GCM ciphertext of headers dict JSON)
- `command` keeps NOT NULL — HTTP rows write `'__http__'` placeholder (avoid migration of existing constraint)
- Schema validators: transport='http' → url required; transport='stdio' → command required (and not '__http__')
- McpServerResponse: when transport='http', show `headers: {Authorization: "Bearer ***"}` mask; never return headers_encrypted ciphertext

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_mcp_http_schema.py`:

```python
"""Tests for MCP HTTP transport schema additions."""
import pytest
from pydantic import ValidationError
from app.schemas.mcp import McpServerCreate, McpServerResponse


def test_create_stdio_requires_command():
    with pytest.raises(ValidationError):
        McpServerCreate(name="x", transport="stdio", url=None)


def test_create_http_requires_url():
    with pytest.raises(ValidationError):
        McpServerCreate(name="x", transport="http", command="__http__")


def test_create_http_with_url_ok():
    m = McpServerCreate(
        name="x", transport="http", url="https://mcp.example/mcp",
        command="__http__", args=[], env={},
        headers={"Authorization": "Bearer abc"},
    )
    assert m.transport == "http"


def test_response_masks_authorization():
    r = McpServerResponse(
        id="00000000-0000-0000-0000-000000000000",
        name="x", scope="system", transport="http",
        url="https://example/mcp", command="__http__",
        args=[], env={},
        headers={"Authorization": "Bearer secret-abc-123", "Content-Type": "application/json"},
    )
    d = r.model_dump()
    assert d["headers"]["Authorization"] == "Bearer ***"
    assert d["headers"]["Content-Type"] == "application/json"  # non-sensitive unchanged
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
pytest tests/test_mcp_http_schema.py -v
```
Expected: FAIL — schema fields don't exist.

- [ ] **Step 3: Update model**

Modify `backend/app/models/mcp_server.py` `McpServer` class — append fields:

```python
# After existing fields, before relationships:
transport: Mapped[str] = mapped_column(
    String(20), nullable=False, default="stdio", server_default="stdio"
)
url: Mapped[str | None] = mapped_column(Text, nullable=True)
headers_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Write alembic migration**

Create `backend/alembic/versions/010_mcp_http_transport.py`:

```python
"""mcp_http_transport: add transport/url/headers_encrypted to mcp_servers.

Revision ID: 010_mcp_http
Revises: 009_plugin_typed_columns
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa


revision = "010_mcp_http"
down_revision = "009_plugin_typed_columns"
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
```

- [ ] **Step 5: Update Pydantic schemas**

Modify `backend/app/schemas/mcp.py`:

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class McpServerBase(BaseModel):
    name: str
    description: str | None = None
    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None
    headers: dict[str, str] | None = None  # plaintext (encrypted on write to DB)


class McpServerCreate(McpServerBase):
    @model_validator(mode="after")
    def _validate_transport_fields(self):
        if self.transport == "stdio":
            if not self.command or self.command == "__http__":
                raise ValueError("stdio transport requires a real command")
        elif self.transport == "http":
            if not self.url:
                raise ValueError("http transport requires url")
            if not self.command:
                self.command = "__http__"  # placeholder for NOT NULL DB column
        return self


class McpServerUpdate(McpServerBase):
    name: str | None = None  # all optional on update


_SENSITIVE_HEADER_KEYS = {"authorization", "x-api-key", "api-key", "x-auth-token", "cookie"}


class McpServerResponse(McpServerBase):
    id: str
    scope: str

    @field_validator("headers")
    @classmethod
    def _mask_sensitive_headers(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return None
        out = {}
        for k, val in v.items():
            if k.lower() in _SENSITIVE_HEADER_KEYS:
                # Preserve scheme prefix (Bearer / Basic) + mask value
                parts = (val or "").split(" ", 1)
                if len(parts) == 2:
                    out[k] = f"{parts[0]} ***"
                else:
                    out[k] = "***"
            else:
                out[k] = val
        return out
```

(Adjust to existing schema file structure — append fields to existing classes if they exist; this listing shows the resulting shape.)

- [ ] **Step 6: Update frontend admin.html MCP servers tab**

Find the existing MCP server form in `admin.html` (search for the existing stdio command/args/env inputs) and add:

```html
<!-- Transport selector -->
<label>
  <input type="radio" name="transport" value="stdio" checked> Stdio (子进程)
</label>
<label>
  <input type="radio" name="transport" value="http"> HTTP (Streamable + SSE)
</label>

<!-- Conditional: stdio fields visible when transport=stdio -->
<div data-when-transport="stdio">
  <input name="command" placeholder="例：npx" />
  <input name="args" placeholder='["-y", "@modelcontextprotocol/server-brave-search"]' />
  <textarea name="env" placeholder='{"BRAVE_API_KEY": "xxx"}'></textarea>
</div>

<!-- Conditional: http fields visible when transport=http -->
<div data-when-transport="http" style="display:none">
  <input name="url" placeholder="https://mcp.exa.ai/mcp" />
  <textarea name="headers" placeholder='{"Authorization": "Bearer xxx"}'></textarea>
</div>
```

Add JS to toggle visibility on radio change. When `transport=http` selected, `command` field is hidden and value auto-set to `"__http__"`.

For display of existing http servers: when rendering an http server, show `Authorization: Bearer ***` (masked from API; no client-side unmask).

- [ ] **Step 7: Run alembic upgrade + tests**

```bash
cd backend && alembic upgrade head
pytest tests/test_mcp_http_schema.py -v
```
Expected: migration succeeds; 4/4 schema tests PASS.

Verify migration in DB:
```sql
\d mcp_servers
-- Should show transport (varchar(20) default 'stdio') / url (text) / headers_encrypted (text)
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/mcp_server.py backend/app/schemas/mcp.py backend/alembic/versions/010_mcp_http_transport.py backend/tests/test_mcp_http_schema.py frontend/admin.html
git commit -m "feat(mcp): add HTTP transport schema (transport/url/headers_encrypted)

- alembic 010 adds 3 nullable columns to mcp_servers
- Pydantic validators: stdio requires command, http requires url
- McpServerResponse masks Authorization/X-API-Key/X-Auth-Token in display
- admin.html MCP tab gets transport radio + conditional stdio/http fields

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 (W5): L5b — MCPClient HTTP Streamable transport + host.py dispatch

**Files:**
- Modify: `executor/plugins/mcp_client.py` (add HTTP branch — keep stdio branch intact)
- Modify: `executor/plugins/host.py` (`_start_mcp_server` dispatch on transport)
- Create: `executor/tests/test_mcp_client_http.py`
- Create: `executor/tests/test_plugin_host_dispatch.py`

**Decision context:**
- MCP spec 2025-03-26 Streamable HTTP: POST JSON-RPC + `Accept: application/json, text/event-stream` → server responds either `application/json` (single response) or `text/event-stream` (streamed messages). Persist `Mcp-Session-Id` from initial response, attach to all subsequent calls. On 410 (session expired) → re-initialize.
- Use `httpx.AsyncClient` (already in project deps) for POST + SSE consumption.
- JSON-RPC framing per spec: `{"jsonrpc": "2.0", "id": int, "method": str, "params": dict}` request; SSE message frames are `event: message\ndata: <jsonrpc-payload>\n\n`.

- [ ] **Step 1: Write failing tests**

Create `executor/tests/test_mcp_client_http.py`:

```python
"""Tests for MCPClient HTTP Streamable transport branch."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from executor.plugins.mcp_client import MCPClient


@pytest.mark.asyncio
async def test_http_init_persists_session_id(httpx_mock):
    """Initialize POST → SSE response with Mcp-Session-Id header → client stores it."""
    httpx_mock.add_response(
        method="POST",
        url="https://mcp.example/mcp",
        headers={"Mcp-Session-Id": "session-abc-123", "content-type": "text/event-stream"},
        text=(
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"0"}}}\n\n'
        ),
    )
    client = MCPClient(
        name="test", transport="http",
        url="https://mcp.example/mcp",
        headers={"Authorization": "Bearer x"},
    )
    await client.start()
    assert client.session_id == "session-abc-123"


@pytest.mark.asyncio
async def test_http_list_tools_parses_sse(httpx_mock):
    """list_tools → server returns tools array via SSE → client decodes."""
    httpx_mock.add_response(
        method="POST",
        url="https://mcp.example/mcp",
        headers={"Mcp-Session-Id": "s1", "content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}}}\n\n',
    )
    httpx_mock.add_response(
        method="POST",
        url="https://mcp.example/mcp",
        headers={"content-type": "text/event-stream"},
        text=(
            'event: message\n'
            'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search","description":"x"},{"name":"fetch","description":"y"}]}}\n\n'
        ),
    )
    client = MCPClient(name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    tools = await client.list_tools()
    names = {t["name"] if isinstance(t, dict) else t.name for t in tools}
    assert names == {"web_search", "fetch"}


@pytest.mark.asyncio
async def test_http_410_triggers_reinitialize(httpx_mock):
    """410 Gone on tool call → client clears session_id + reinitialize on next call."""
    httpx_mock.add_response(  # initial init
        method="POST", url="https://mcp.example/mcp",
        headers={"Mcp-Session-Id": "s-old", "content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n',
    )
    httpx_mock.add_response(method="POST", url="https://mcp.example/mcp", status_code=410)
    httpx_mock.add_response(  # reinit after 410
        method="POST", url="https://mcp.example/mcp",
        headers={"Mcp-Session-Id": "s-new", "content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n',
    )
    httpx_mock.add_response(  # retried tool call
        method="POST", url="https://mcp.example/mcp",
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":3,"result":{"tools":[]}}\n\n',
    )
    client = MCPClient(name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    assert client.session_id == "s-old"
    tools = await client.list_tools()
    assert client.session_id == "s-new"
    assert tools == []
```

Create `executor/tests/test_plugin_host_dispatch.py`:

```python
"""Tests for PluginHost dispatching stdio vs http transport."""
import pytest
from unittest.mock import AsyncMock, patch
from executor.plugins.host import PluginHost


@pytest.mark.asyncio
async def test_load_stdio_plugin_uses_stdio_branch(tmp_path):
    """Plugin config transport=stdio → MCPClient stdio branch path called."""
    fake_client = AsyncMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[])
    with patch("executor.plugins.host.MCPClient") as MockClient:
        MockClient.return_value = fake_client
        host = PluginHost()
        await host._start_mcp_server({
            "name": "test",
            "transport": "stdio",
            "command": "echo",
            "args": ["hi"],
            "env": {},
        })
        # Verify constructor got transport=stdio
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["transport"] == "stdio"
        assert call_kwargs["command"] == "echo"


@pytest.mark.asyncio
async def test_load_http_plugin_uses_http_branch():
    """Plugin config transport=http → MCPClient http branch path called."""
    fake_client = AsyncMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[])
    with patch("executor.plugins.host.MCPClient") as MockClient:
        MockClient.return_value = fake_client
        host = PluginHost()
        await host._start_mcp_server({
            "name": "test",
            "transport": "http",
            "url": "https://mcp.example/mcp",
            "headers": {"Authorization": "Bearer x"},
        })
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["transport"] == "http"
        assert call_kwargs["url"] == "https://mcp.example/mcp"
        assert "Authorization" in call_kwargs["headers"]
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd .worktrees/plugin-bootstrap && pytest executor/tests/test_mcp_client_http.py executor/tests/test_plugin_host_dispatch.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement HTTP branch in MCPClient**

Modify `executor/plugins/mcp_client.py`. Add HTTP branch alongside existing stdio:

```python
# At top of file, ensure imports:
import httpx
import json
import asyncio
from typing import Any


class MCPClient:
    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        # stdio fields
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        # http fields
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.url = url
        self.headers = headers or {}
        self.session_id: str | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._next_id = 1
        # ... existing stdio fields preserved (process, reader, writer, etc.)

    async def start(self) -> None:
        if self.transport == "http":
            await self._start_http()
        else:
            await self._start_stdio()  # existing impl

    async def _start_http(self) -> None:
        """Initialize MCP session over HTTP Streamable transport."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        result = await self._http_request({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "prism-executor", "version": "0.1"},
            },
        })
        self._next_id += 1
        # Capabilities stored if needed; serverInfo logged
        # session_id captured in _http_request from response headers

    async def _http_request(self, payload: dict, retry_on_410: bool = True) -> Any:
        """Send JSON-RPC over HTTP, parse SSE response, return result."""
        if self._http_client is None:
            raise RuntimeError("HTTP client not started")
        req_headers = dict(self.headers)
        req_headers["Content-Type"] = "application/json"
        req_headers["Accept"] = "application/json, text/event-stream"
        if self.session_id:
            req_headers["Mcp-Session-Id"] = self.session_id

        resp = await self._http_client.post(self.url, json=payload, headers=req_headers)
        if resp.status_code == 410 and retry_on_410:
            # session expired — clear and reinit, then retry
            self.session_id = None
            await self._start_http()
            return await self._http_request(payload, retry_on_410=False)
        resp.raise_for_status()
        # Capture session id from any response that includes it
        new_session = resp.headers.get("Mcp-Session-Id")
        if new_session:
            self.session_id = new_session

        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            # Parse SSE: lines like "event: message\ndata: {...}\n\n"
            return self._parse_sse_for_result(resp.text, payload["id"])
        elif "application/json" in ctype:
            data = resp.json()
            return data.get("result") if data.get("id") == payload["id"] else None
        return None

    def _parse_sse_for_result(self, body: str, expected_id: int) -> Any:
        """Extract the JSON-RPC result whose id matches expected_id from SSE body."""
        for block in body.split("\n\n"):
            if not block.strip():
                continue
            data_lines = [ln[6:] for ln in block.splitlines() if ln.startswith("data: ")]
            if not data_lines:
                continue
            data = json.loads("\n".join(data_lines))
            if data.get("id") == expected_id and "result" in data:
                return data["result"]
        return None

    async def list_tools(self) -> list[dict]:
        if self.transport == "http":
            res = await self._http_request({
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/list",
                "params": {},
            })
            self._next_id += 1
            return (res or {}).get("tools", [])
        else:
            return await self._list_tools_stdio()  # existing

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if self.transport == "http":
            res = await self._http_request({
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            self._next_id += 1
            return res
        else:
            return await self._call_tool_stdio(name, arguments)

    async def stop(self) -> None:
        if self.transport == "http":
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
        else:
            await self._stop_stdio()  # existing
```

> Existing stdio methods preserved as `_start_stdio`, `_list_tools_stdio`, `_call_tool_stdio`, `_stop_stdio`. Implementer renames the existing methods to use `_stdio` suffix and routes from the new public `start/list_tools/call_tool/stop` methods.

- [ ] **Step 4: Implement host.py dispatch**

Modify `executor/plugins/host.py`. Locate `_start_mcp_server`. Update to:

```python
async def _start_mcp_server(self, server_config: dict) -> None:
    """Dispatch on transport: stdio (existing) or http (new)."""
    transport = server_config.get("transport", "stdio")
    if transport == "http":
        client = MCPClient(
            name=server_config["name"],
            transport="http",
            url=server_config["url"],
            headers=server_config.get("headers", {}),
        )
    else:
        client = MCPClient(
            name=server_config["name"],
            transport="stdio",
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env", {}),
        )
    await client.start()
    # ... existing tool registration logic on returned tools (preserved as before)
    self._clients[server_config["name"]] = client
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
pytest executor/tests/test_mcp_client_http.py executor/tests/test_plugin_host_dispatch.py -v
# Also re-run existing stdio tests to confirm no regression
pytest executor/tests/ -k "mcp_client or plugin_host" -v
```
Expected: All new tests PASS, existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add executor/plugins/mcp_client.py executor/plugins/host.py executor/tests/test_mcp_client_http.py executor/tests/test_plugin_host_dispatch.py
git commit -m "feat(mcp): MCPClient HTTP Streamable transport (spec 2025-03-26)

- HTTP branch: POST JSON-RPC + SSE response + Mcp-Session-Id stateful + 410 reinit
- host.py _start_mcp_server dispatches on transport field
- stdio branch unchanged (renamed internal methods to _stdio suffix)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 (W6): L2 + L6 — Executor bootstrap + exa builtin

**Files:**
- Modify: `executor/__main__.py` Step 3d (lines 491-509)
- Modify: `backend/app/services/mcp_service.py` (add exa entry to `_BUILTIN_MCP_SERVERS` + handle headers_template encryption)
- Create: `executor/tests/test_plugin_bootstrap_main.py`
- Create: `backend/tests/test_mcp_builtin_exa.py`

**Decision context:**
- Step 3d: after registry/assembler created, fetch installed-skills + mcp-servers via internal endpoints (CALLBACK_SECRET passed via env from process_manager), instantiate PluginHost + SkillLoader, call load_plugin per server (registers tools), call SkillLoader.load_skills with user-installed list (filter), then `assembler.update_tools(registry.list_definitions())` + inject skills into PromptAssembler
- Failure handling: log warning + continue (don't crash run if backend unreachable)
- exa entry uses `transport=http`, `url=https://mcp.exa.ai/mcp`, `headers_template={"Authorization": "Bearer ${env:EXA_API_KEY}", "Content-Type": "application/json"}`
- `register_builtin_servers` for HTTP entries: substitute env vars in headers_template, encrypt result via `encrypt_value`, store as headers_encrypted

- [ ] **Step 1: Write failing tests**

Create `executor/tests/test_plugin_bootstrap_main.py`:

```python
"""Tests for executor __main__ Step 3d plugin bootstrap section."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_bootstrap_fetches_skills_and_mcp_servers(monkeypatch):
    """Bootstrap function calls both internal endpoints with CALLBACK_SECRET."""
    monkeypatch.setenv("CALLBACK_SECRET", "test-secret-abc")

    fake_skills = [{"skill_name": "git-helper", "install_path": "/data/.prism/skills/@local/git-helper", "source": "local", "source_url": None, "version": "1.0"}]
    fake_servers = [{"id": "s1", "name": "exa", "scope": "system", "transport": "http", "url": "https://mcp.exa.ai/mcp", "headers": {"Authorization": "Bearer x"}}]

    fake_resp_skills = MagicMock(); fake_resp_skills.json = MagicMock(return_value={"skills": fake_skills}); fake_resp_skills.raise_for_status = MagicMock()
    fake_resp_servers = MagicMock(); fake_resp_servers.json = MagicMock(return_value={"servers": fake_servers}); fake_resp_servers.raise_for_status = MagicMock()

    fake_http = AsyncMock()
    fake_http.get = AsyncMock(side_effect=[fake_resp_skills, fake_resp_servers])

    from executor.__main__ import bootstrap_plugins
    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = fake_http
        skills, servers = await bootstrap_plugins(
            backend_url="http://backend:8000",
            user_id="user-uuid-1",
            callback_secret="test-secret-abc",
        )
    assert skills == fake_skills
    assert servers == fake_servers


@pytest.mark.asyncio
async def test_bootstrap_failure_returns_empty_not_crash(caplog):
    """If backend unreachable, log warning + return ([], []) — don't crash."""
    from executor.__main__ import bootstrap_plugins
    fake_http = AsyncMock()
    fake_http.get = AsyncMock(side_effect=Exception("connection refused"))
    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = fake_http
        skills, servers = await bootstrap_plugins(
            backend_url="http://backend:8000",
            user_id="user-uuid-1",
            callback_secret="x",
        )
    assert skills == []
    assert servers == []
    assert any("plugin_bootstrap_failed" in r.message or "plugin_bootstrap" in r.name for r in caplog.records)
```

Create `backend/tests/test_mcp_builtin_exa.py`:

```python
"""Tests for exa HTTP builtin entry."""
import os
import pytest
from app.services.mcp_service import MCPService, _BUILTIN_MCP_SERVERS


def test_exa_in_builtins():
    names = {s["name"] for s in _BUILTIN_MCP_SERVERS}
    assert "exa" in names
    exa = next(s for s in _BUILTIN_MCP_SERVERS if s["name"] == "exa")
    assert exa["transport"] == "http"
    assert exa["url"] == "https://mcp.exa.ai/mcp"


def test_register_skips_exa_if_no_key(db, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    from app.models.mcp_server import McpServer
    db.query(McpServer).filter_by(name="exa").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    assert db.query(McpServer).filter_by(name="exa").first() is None


def test_register_creates_exa_with_encrypted_headers(db, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key-xyz")
    from app.models.mcp_server import McpServer
    from app.core.security import decrypt_value
    from app.core.config import settings
    import json
    db.query(McpServer).filter_by(name="exa").delete(); db.commit()
    MCPService(db).register_builtin_servers()
    row = db.query(McpServer).filter_by(name="exa").first()
    assert row is not None
    assert row.transport == "http"
    assert row.url == "https://mcp.exa.ai/mcp"
    assert row.headers_encrypted is not None
    plaintext = decrypt_value(row.headers_encrypted, settings.ENCRYPTION_KEY)
    headers = json.loads(plaintext)
    assert headers["Authorization"] == "Bearer exa-test-key-xyz"
    assert headers["Content-Type"] == "application/json"
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
pytest executor/tests/test_plugin_bootstrap_main.py backend/tests/test_mcp_builtin_exa.py -v
```
Expected: FAIL.

- [ ] **Step 3: Add bootstrap_plugins helper to __main__.py + Step 3d integration**

Modify `executor/__main__.py`. Add at module level (above `_run_main` or wherever helpers live):

```python
async def bootstrap_plugins(
    backend_url: str,
    user_id: str,
    callback_secret: str,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch user-installed skills + accessible MCP servers from backend internal API.

    Returns (skills, servers) — both empty list on any failure (graceful, log warning).
    """
    import httpx
    headers = {"X-Callback-Secret": callback_secret}
    skills: list[dict] = []
    servers: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp_skills = await http.get(f"{backend_url}/api/v1/internal/users/{user_id}/installed-skills", headers=headers)
            resp_skills.raise_for_status()
            skills = resp_skills.json().get("skills", [])
            resp_servers = await http.get(f"{backend_url}/api/v1/internal/users/{user_id}/mcp-servers", headers=headers)
            resp_servers.raise_for_status()
            servers = resp_servers.json().get("servers", [])
    except Exception as exc:
        logger.warning("executor.plugin_bootstrap_failed", error=str(exc), user_id=user_id)
    return skills, servers
```

Then in Step 3d (after `pipeline = ToolExecutionPipeline(...)`, before HarnessRuntime), insert:

```python
# ----------------------------------------------------------------
# Step 3d-bis: Plugin Bootstrap (skills + MCP servers)
# ----------------------------------------------------------------
from executor.plugins.host import PluginHost
from executor.plugins.skill_loader import SkillLoader

callback_secret = os.environ.get("CALLBACK_SECRET", "")
skills_data, servers_data = await bootstrap_plugins(
    backend_url=os.environ.get("BACKEND_URL", "http://backend:8000"),
    user_id=args.user_id,
    callback_secret=callback_secret,
)

plugin_host = PluginHost(registry=registry, assembler=assembler)
for srv in servers_data:
    try:
        await plugin_host._start_mcp_server(srv)
    except Exception as exc:
        logger.warning("executor.mcp_load_failed", server=srv.get("name"), error=str(exc))

skill_loader = SkillLoader()
loaded_skill_infos = []
for s in skills_data:
    try:
        loaded = skill_loader.load_skill_from_path(s["install_path"], skill_name=s["skill_name"])
        if loaded is not None:
            loaded_skill_infos.append(loaded)
    except Exception as exc:
        logger.warning("executor.skill_load_failed", skill=s.get("skill_name"), error=str(exc))

# Refresh assembler with newly registered tools + skills (ADR-046)
assembler.update_tools(registry.list_definitions())
assembler.skills = loaded_skill_infos  # PromptAssembler now references loaded skills
```

> If `SkillLoader.load_skill_from_path` doesn't exist, implementer adds a thin method that reads `<install_path>/SKILL.md`, parses frontmatter via existing helpers, and returns `SkillInfo`.

- [ ] **Step 4: Add exa to _BUILTIN_MCP_SERVERS**

Modify `backend/app/services/mcp_service.py`. Append to `_BUILTIN_MCP_SERVERS`:

```python
{
    "name": "exa",
    "description": "Exa AI 搜索 — 神经网络驱动的语义搜索 + URL 内容提取（HTTP transport）。",
    "transport": "http",
    "url": "https://mcp.exa.ai/mcp",
    "headers_template": {
        "Authorization": "Bearer ${env:EXA_API_KEY}",
        "Content-Type": "application/json",
    },
    "env_var": "EXA_API_KEY",
},
```

Update `register_builtin_servers()` to handle http entries:

```python
def register_builtin_servers(self) -> None:
    import os
    import json as _json
    import re
    from app.core.security import encrypt_value
    from app.core.config import settings as _settings

    for spec in _BUILTIN_MCP_SERVERS:
        env_var = spec.get("env_var")
        api_key = os.environ.get(env_var) if env_var else None
        if env_var and not api_key:
            logger.info("mcp.builtin.skipped", name=spec["name"], reason=f"{env_var} not set")
            continue

        transport = spec.get("transport", "stdio")
        if transport == "http":
            template = spec.get("headers_template", {})
            # substitute ${env:VAR}
            def _sub(s: str) -> str:
                return re.sub(r"\$\{env:(\w+)\}", lambda m: os.environ.get(m.group(1), ""), s)
            headers = {k: _sub(v) for k, v in template.items()}
            ciphertext = encrypt_value(_json.dumps(headers), _settings.ENCRYPTION_KEY)
            row_kwargs = dict(
                name=spec["name"],
                description=spec.get("description"),
                scope="system",
                command="__http__",
                args=[],
                env={},
                transport="http",
                url=spec["url"],
                headers_encrypted=ciphertext,
            )
        else:
            row_kwargs = dict(
                name=spec["name"],
                description=spec.get("description"),
                scope="system",
                command=spec["command"],
                args=spec.get("args", []),
                env={env_var: api_key} if env_var else {},
                transport="stdio",
                url=None,
                headers_encrypted=None,
            )

        existing = self.db.query(McpServer).filter_by(name=spec["name"], scope="system").first()
        if existing:
            for k, v in row_kwargs.items():
                setattr(existing, k, v)
            self.db.commit()
            continue
        row = McpServer(**row_kwargs)
        self.db.add(row)
        self.db.commit()
        logger.info("mcp.builtin.registered", name=spec["name"], transport=transport)
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
pytest executor/tests/test_plugin_bootstrap_main.py backend/tests/test_mcp_builtin_exa.py -v
```
Expected: 5/5 PASS.

- [ ] **Step 6: Smoke check executor starts without crash on empty plugin list**

```bash
# Simulate empty plugin response by hitting a fresh user
# (backend must be running for this; defer to Batch 3 e2e)
echo "Smoke: see Task 7 e2e for full integration verification"
```

- [ ] **Step 7: Commit**

```bash
git add executor/__main__.py backend/app/services/mcp_service.py executor/tests/test_plugin_bootstrap_main.py backend/tests/test_mcp_builtin_exa.py
git commit -m "feat(executor): bootstrap PluginHost + SkillLoader on Step 3d (root cause fix)

- bootstrap_plugins() fetches user-installed skills+mcp-servers via CALLBACK_SECRET
- PluginHost loads each server; SkillLoader loads each skill by install_path
- assembler.update_tools() registers MCP tools into prompt
- Failure graceful (log warn + continue) — no run crash on backend hiccup
- exa builtin entry: transport=http, headers_template substitutes EXA_API_KEY env var,
  AES-256-GCM encrypted before DB write

Resurrects Skills + MCP runtime (root cause: __main__.py never instantiated PluginHost).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 (W7): L8 — e2e Playwright real-call validation (qa-engineer)

**Files:**
- Create: `e2e/tests/plugin-bootstrap-real-call.spec.ts`
- Test artifacts under `e2e/test-results/plugin-bootstrap/`

**Decision context:**
- Real call against live exa MCP via user's existing API key (`EXA_API_KEY` in `.env`)
- Both desktop (1280×720) and mobile (390×844) viewports
- Asserts agent **really invokes** `mcp__exa__web_search_exa` (not "I cannot search")
- Asserts tool_result contains URLs from real exa response

- [ ] **Step 1: Pre-conditions checklist**

Verify before running:
- `.env` has `EXA_API_KEY=24b74e9a-d7e5-4621-b10d-46e7ea44bb65`
- `docker compose -p prismv3 up -d --build --force-recreate backend executor` (so Dockerfile + Migration 010 land)
- `alembic upgrade head` applied
- `register_builtin_servers()` ran on backend startup (lifespan)

- [ ] **Step 2: Write Playwright spec**

Create `e2e/tests/plugin-bootstrap-real-call.spec.ts`:

```typescript
import { test, expect, devices } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop", viewport: { width: 1280, height: 720 } },
  { name: "mobile-iphone14", ...devices["iPhone 14 Pro"] },
];

for (const cfg of VIEWPORTS) {
  test.describe(`plugin-bootstrap @${cfg.name}`, () => {
    test.use({ viewport: cfg.viewport });

    test("admin sees exa registered as system MCP server", async ({ page }) => {
      await page.goto("/admin.html");
      await page.fill('input[name="email"]', "admin@prism.dev");
      await page.fill('input[name="password"]', "PrismAdmin!2026");
      await page.click('button[type="submit"]');
      await page.click('text=MCP 服务器');
      // exa should be auto-registered from .env EXA_API_KEY
      await expect(page.locator('text=exa').first()).toBeVisible({ timeout: 8_000 });
      await expect(page.locator('text=https://mcp.exa.ai/mcp').first()).toBeVisible();
    });

    test("user asks for AI news → agent calls mcp__exa__web_search_exa with real result", async ({ page }) => {
      await page.goto("/Prism.html");
      await page.fill('input[name="email"]', "user@prism.dev");
      await page.fill('input[name="password"]', "PrismUser!2026");
      await page.click('button[type="submit"]');

      // Open new chat
      await page.click('text=新会话');
      const composer = page.locator('textarea[name="prompt"]');
      await composer.fill("请搜索：今天 AI 行业有什么重要新闻？给我 3 条带链接。");
      await page.keyboard.press("Enter");

      // Wait up to 60s for SSE stream to complete
      await expect(page.locator('[data-testid="message-complete"]').last()).toBeVisible({ timeout: 60_000 });

      // Assert tool_use block for mcp__exa__web_search_exa exists
      const toolUseBlock = page.locator('[data-tool-name^="mcp__exa__"]').first();
      await expect(toolUseBlock).toBeVisible({ timeout: 5_000 });
      const toolName = await toolUseBlock.getAttribute("data-tool-name");
      expect(toolName).toMatch(/^mcp__exa__/);

      // Assert tool_result rendered URLs (real exa results contain https://)
      const toolResult = page.locator('[data-testid="tool-result"]').first();
      const resultText = await toolResult.textContent();
      expect(resultText).toMatch(/https?:\/\/[^\s]+/);

      // Assert assistant message references actual content (not refusal)
      const lastMsg = await page.locator('[data-role="assistant"]').last().textContent();
      expect(lastMsg).not.toMatch(/我.*不能.*搜索|无法访问/);
      expect(lastMsg).toMatch(/https?:\/\//); // at least one real URL cited
    });

    test("invalid EXA_API_KEY → server inactive → search request gracefully degraded", async ({ page, context }) => {
      // This test requires admin to flip the exa server's headers via UI or skip if no UI
      test.skip(true, "Requires admin UI editing of headers — verify manually with bad key in .env");
    });
  });
}
```

- [ ] **Step 3: Run e2e**

```bash
cd e2e && BASE_URL=http://localhost:8000 npx playwright test plugin-bootstrap-real-call.spec.ts --project=chromium --reporter=list
```
Expected: All non-skipped tests PASS in both viewports (~4 effective tests). Real-call test runs ~30-60s due to LLM round-trip.

If the agent doesn't call exa:
- Check assembler.update_tools logs in executor: did `mcp__exa__web_search_exa` appear in tools list?
- Check internal endpoint response: did `/internal/users/{uid}/mcp-servers` return exa?
- Check user has installed exa (UserMcpInstall row exists for that user)

- [ ] **Step 4: Capture screenshots + commit**

```bash
git add e2e/tests/plugin-bootstrap-real-call.spec.ts
git commit -m "test(e2e): plugin bootstrap real-call validation

Double-viewport (desktop + iPhone 14 Pro). Asserts agent truly invokes
mcp__exa__web_search_exa and renders real URLs in response.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (Spec Coverage Check)

| Spec Requirement | Implemented in Task |
|---|---|
| Backend internal endpoints (skills + mcp servers) | Task 1 |
| HTTP transport DB schema | Task 4 |
| HTTP MCPClient branch | Task 5 |
| Executor PluginHost+SkillLoader bootstrap | Task 6 |
| exa builtin (HTTP) | Task 6 |
| Brave + Tavily builtins (stdio) | Task 3 |
| `test_server` real connection | Task 2 |
| Default marketplace bootstrap | Task 3 |
| Dockerfile nodejs install | Task 3 |
| Frontend admin transport selector | Task 4 |
| Headers AES-256-GCM encryption | Tasks 4 + 6 |
| CALLBACK_SECRET auth | Task 1 |
| e2e Playwright double-viewport real-call | Task 7 |

**Type/signature consistency check:**
- `MCPClient(name, transport, command|url, args|headers, env|url, ...)` — same kwargs across tasks 2/5/6 ✓
- `_BUILTIN_MCP_SERVERS` entries: each has `name, description`; stdio has `command/args/env_var`; http has `url/headers_template/env_var` ✓
- `bootstrap_plugins(backend_url, user_id, callback_secret) -> (skills, servers)` consistent in tests + impl ✓
- `headers_encrypted: str | None` (TEXT, AES-256-GCM ciphertext) consistent in model + schema + tasks 1+6 ✓

**Placeholder scan:** No "TBD"/"TODO"/"implement later" left.

**Scope check:** Single coherent feature (plugin bootstrap) — fits one PR.

---

## Execution Handoff

After this plan is committed, main agent dispatches workers via subagent-driven-development:

**Batch 1 (parallel sonnet x4)**: Task 1 → W1, Task 2 → W2, Task 3 → W3, Task 4 → W4

**Batch 2 (parallel sonnet x2)**: Task 5 → W5, Task 6 → W6 (depends on Batch 1)

**Batch 3 (qa-engineer)**: Task 7 → W7 (depends on Batch 2)

Between batches: main agent integrates, verifies tests pass, updates handoff files at `.claude/plans/handoff-<from>-to-<to>-<topic>.md`.

After Batch 3: `simplify` (3-subagent reuse/quality/efficiency) → `project-review:pjr` → `superpowers:requesting-code-review` → `git-merge-to-develop:git-merge-to-develop`.
