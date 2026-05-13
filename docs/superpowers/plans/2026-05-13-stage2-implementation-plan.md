# Stage 2: Poco Quality Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 7 features to reach competitive parity with Poco — workspace isolation, client pooling, MCP injection, interactive permissions, prompt composition, log masking, IM gateway.

**Architecture:** All changes in executor_v2/ (subprocess) and backend/app/ (FastAPI). Process boundary preserved: executor never imports backend code. Communication via HTTP callbacks + Redis pub/sub.

**Tech Stack:** Python 3.12, FastAPI, claude-agent-sdk, Redis, PostgreSQL, structlog

---

## File Structure

### New files
- `executor_v2/prompt.py` — PromptAssembler (multi-segment system prompt builder)
- `executor_v2/masking.py` — SecretMasker (structlog processor + callback body filter)

### Modified files
- `executor_v2/__main__.py` — workspace dir, MCP config parsing, prompt assembler
- `executor_v2/runtime.py` — permission_mode, MCP servers in ClaudeAgentOptions
- `executor_v2/config.py` — RunConfig adds mcp_servers field
- `executor_v2/callbacks.py` — permission_ask method, masking integration
- `executor_v2/hooks/builtin/permission.py` — rewrite: allowlist + BLPOP approval flow
- `backend/app/services/process_manager.py` — workspace mkdir, MCP query, env passing
- `backend/app/observability/logging.py` — masking processor injection
- `docker-compose.yml` — workspace volume mount

---

## Batch A: Independent Tasks (parallel)

### Task 1: Workspace Management (#8)

**Files:**
- Modify: `backend/app/services/process_manager.py`
- Modify: `docker-compose.yml`
- Modify: `executor_v2/config.py`

- [ ] **Step 1: Add workspace volume to docker-compose.yml**

In `docker-compose.yml`, add a named volume and mount it in the backend service:

```yaml
volumes:
  pgdata:
  prism-backend-data:
  redis-data:
  workspace-data:    # NEW
```

In the `backend` service `volumes:` section, add:

```yaml
      - workspace-data:/workspace
```

- [ ] **Step 2: Create workspace directory in ProcessManager**

In `backend/app/services/process_manager.py`, in `_run_in_thread()`, after fetching the run row and before `_build_command()`, add workspace creation:

```python
        workspace_dir = f"/workspace/{run_row.session_id}"
        os.makedirs(workspace_dir, exist_ok=True)
```

Then pass it to `_build_command`:

```python
        cmd = self._build_command(run_row, resume_from_step=resume_from_step, workspace_dir=workspace_dir)
```

- [ ] **Step 3: Update _build_command to pass workspace**

Add `workspace_dir` parameter to `_build_command()` signature and add to env:

```python
    def _build_env(self, workspace_dir: str = "/tmp") -> dict[str, str]:
        env = os.environ.copy()
        env["ENCRYPTION_KEY"] = self._settings.ENCRYPTION_KEY
        env["WORKSPACE_PATH"] = workspace_dir
        return env
```

Update `_run_in_thread` to pass `workspace_dir` to `_build_env`:

```python
        env = self._build_env(workspace_dir=workspace_dir)
```

- [ ] **Step 4: Verify config.py reads WORKSPACE_PATH**

`executor_v2/config.py` already reads `os.environ.get("WORKSPACE_PATH", "/tmp")` at line 107. Confirm this flows into `RunConfig.workspace_path` → `runtime.py` `_build_options()` `cwd=`.

- [ ] **Step 5: Build and test**

```bash
docker compose build backend
docker compose up -d backend --force-recreate
# Submit a task and verify the workspace directory is created
docker exec <backend-container> ls -la /workspace/
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/process_manager.py docker-compose.yml
git commit -m "feat(workspace): per-session /workspace/{session_id} isolation"
```

---

### Task 2: Prompt Composition (#12)

**Files:**
- Create: `executor_v2/prompt.py`
- Modify: `executor_v2/__main__.py`

- [ ] **Step 1: Create PromptAssembler**

```python
# executor_v2/prompt.py
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PromptSegment:
    header: str
    content: str


class PromptAssembler:
    def __init__(self) -> None:
        self._segments: list[PromptSegment] = []

    def add_base(self, agent_type: str) -> None:
        role_map = {
            "chat": "You are a helpful AI assistant.",
            "explore": "You are a code exploration assistant. Read and analyze code, but do not modify it.",
            "build": "You are a software engineering assistant. Write clean, tested code.",
            "coordinator": "You coordinate multi-step tasks by breaking them into subtasks.",
        }
        text = role_map.get(agent_type, role_map["chat"])
        self._segments.append(PromptSegment(header="Role", content=text))

    def add_workspace(self, workspace_path: str) -> None:
        if not workspace_path or workspace_path == "/tmp":
            return
        try:
            items = sorted(os.listdir(workspace_path))[:20]
        except OSError:
            return
        if not items:
            return
        listing = "\n".join(f"- {item}" for item in items)
        self._segments.append(PromptSegment(
            header="Workspace",
            content=f"Current directory: `{workspace_path}`\n{listing}",
        ))

    def add_memories(self, memories: list[dict]) -> None:
        if not memories:
            return
        lines = []
        for m in memories:
            text = m.get("memory", m.get("text", ""))
            if text:
                lines.append(f"- {text}")
        if lines:
            self._segments.append(PromptSegment(
                header="About the User",
                content="You already know:\n" + "\n".join(lines),
            ))

    def add_skill(self, skill_prompt: str) -> None:
        if skill_prompt:
            self._segments.append(PromptSegment(header="Task Guidelines", content=skill_prompt))

    def add_constraints(self, constraints: str) -> None:
        if constraints:
            self._segments.append(PromptSegment(header="Constraints", content=constraints))

    def assemble(self) -> str:
        if not self._segments:
            return ""
        parts = []
        for seg in self._segments:
            parts.append(f"## {seg.header}\n{seg.content}")
        return "\n\n".join(parts)
```

- [ ] **Step 2: Integrate into __main__.py**

Replace the inline prompt assembly in `__main__.py`:

```python
    from executor_v2.prompt import PromptAssembler
    assembler = PromptAssembler()
    assembler.add_base(config.agent_type)
    assembler.add_workspace(config.workspace_path)
    assembler.add_memories(memories)
    assembler.add_skill(skill_prompt)
    # constraints from session config (future: read from DB)
    combined_prompt = assembler.assemble()
```

Remove the old `combined_prompt = "\n\n".join(...)` line.

- [ ] **Step 3: Build and test**

```bash
docker compose build backend
docker compose up -d backend --force-recreate
# Submit a task, check logs for assembled prompt content
```

- [ ] **Step 4: Commit**

```bash
git add executor_v2/prompt.py executor_v2/__main__.py
git commit -m "feat(prompt): PromptAssembler — structured multi-segment system prompt"
```

---

### Task 3: Log Secret Masking (#13)

**Files:**
- Create: `executor_v2/masking.py`
- Modify: `executor_v2/callbacks.py`
- Modify: `backend/app/observability/logging.py`

- [ ] **Step 1: Create SecretMasker**

```python
# executor_v2/masking.py
from __future__ import annotations

import os
import re

_STATIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*\S+"),
]

_env_values: set[str] = set()


def _load_env_secrets() -> None:
    global _env_values
    for key, val in os.environ.items():
        if any(s in key.upper() for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")) and len(val) >= 8:
            _env_values.add(val)


def mask(text: str) -> str:
    if not _env_values:
        _load_env_secrets()
    for val in _env_values:
        if val in text:
            text = text.replace(val, val[:4] + "***")
    for pat in _STATIC_PATTERNS:
        text = pat.sub(lambda m: m.group()[:6] + "***", text)
    return text


def structlog_masker(logger: object, method: str, event_dict: dict) -> dict:
    for key, val in event_dict.items():
        if isinstance(val, str) and len(val) > 10:
            event_dict[key] = mask(val)
    return event_dict
```

- [ ] **Step 2: Inject into executor_v2 structlog**

In `executor_v2/__main__.py`, at the top of `main()` before any logging:

```python
    import structlog
    from executor_v2.masking import structlog_masker
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog_masker,
            structlog.dev.ConsoleRenderer(),
        ],
    )
```

- [ ] **Step 3: Inject into backend structlog**

In `backend/app/observability/logging.py`, add `structlog_masker` to the processor chain. Import from a shared location or duplicate the masker inline (process boundary — executor and backend are separate).

Create `backend/app/observability/masking.py` with identical logic:

```python
# backend/app/observability/masking.py
# Identical to executor_v2/masking.py — process boundary prevents sharing
```

Add to `init_logging()` processor chain before the renderer.

- [ ] **Step 4: Mask callback HTTP body**

In `executor_v2/callbacks.py`, in `_http_post()`, mask the serialized body before sending:

```python
    async def _http_post(self, event_type: str, data: dict) -> None:
        from executor_v2.masking import mask
        import json
        body_str = json.dumps({"run_id": self._run_id, "event_type": event_type, "data": data})
        masked = mask(body_str)
        # ... send masked body
```

Actually, simpler: mask individual string values in data dict recursively before sending.

- [ ] **Step 5: Build and test**

```bash
docker compose build backend
docker compose up -d backend --force-recreate
# Submit a task, grep logs for API key patterns
docker logs <backend-container> 2>&1 | grep -i "sk-"
# Should find no raw API keys
```

- [ ] **Step 6: Commit**

```bash
git add executor_v2/masking.py backend/app/observability/masking.py executor_v2/__main__.py executor_v2/callbacks.py backend/app/observability/logging.py
git commit -m "feat(masking): secret masking in logs and callbacks — API keys never leaked"
```

---

## Batch B: Dependent Tasks (after A)

### Task 4: MCP Server Injection (#10)

**Files:**
- Modify: `backend/app/services/process_manager.py`
- Modify: `executor_v2/config.py`
- Modify: `executor_v2/__main__.py`
- Modify: `executor_v2/runtime.py`

- [ ] **Step 1: Query MCP servers in ProcessManager**

In `_run_in_thread()`, after workspace creation, query user's MCP servers:

```python
        from app.models.mcp_server import McpServer, UserMcpInstall

        mcp_configs = []
        mcp_installs = (
            db.query(UserMcpInstall)
            .join(McpServer)
            .filter(
                UserMcpInstall.user_id == run_row.user_id,
                UserMcpInstall.is_enabled.is_(True),
            )
            .all()
        )
        for install in mcp_installs:
            srv = install.mcp_server
            mcp_configs.append({
                "name": srv.name,
                "transport": srv.transport_type,
                "command": srv.command,
                "args": srv.args or [],
                "url": srv.url,
                "env": srv.env_vars or {},
            })
```

Pass as JSON env var:

```python
        import json
        if mcp_configs:
            env["MCP_SERVERS_JSON"] = json.dumps(mcp_configs)
```

- [ ] **Step 2: Parse MCP config in executor**

In `executor_v2/__main__.py`, after config loading:

```python
    mcp_servers_raw = os.environ.get("MCP_SERVERS_JSON", "")
    mcp_servers: list[dict] = json.loads(mcp_servers_raw) if mcp_servers_raw else []
```

- [ ] **Step 3: Pass MCP servers to ClaudeAgentOptions**

In `executor_v2/runtime.py` `_build_options()`, add `mcp_servers` parameter:

```python
    def __init__(self, config, callback, registry, memory_prompt="", mcp_servers=None):
        ...
        self._mcp_servers = mcp_servers or []
```

In `_build_options()`:

```python
        mcp_dict = {}
        for srv in self._mcp_servers:
            if srv["transport"] == "stdio":
                mcp_dict[srv["name"]] = {
                    "command": srv["command"],
                    "args": srv.get("args", []),
                    "env": srv.get("env", {}),
                }
            elif srv["transport"] in ("sse", "http"):
                mcp_dict[srv["name"]] = {"url": srv["url"]}

        return ClaudeAgentOptions(
            ...
            mcp_servers=mcp_dict if mcp_dict else None,
        )
```

- [ ] **Step 4: Build and test**

Install a test MCP server via API, submit a task, verify the agent can call MCP tools.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/process_manager.py executor_v2/__main__.py executor_v2/runtime.py
git commit -m "feat(mcp): inject user-installed MCP servers into agent SDK"
```

---

### Task 5: Interactive Permissions (#11)

**Files:**
- Modify: `executor_v2/hooks/builtin/permission.py`
- Modify: `executor_v2/callbacks.py`
- Modify: `executor_v2/runtime.py`

- [ ] **Step 1: Add permission_ask to BackendCallback**

In `executor_v2/callbacks.py`:

```python
    async def permission_ask(
        self,
        request_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> str:
        """Send permission request to backend, BLPOP for answer. Returns 'allow' or 'deny'."""
        await self._http_post("permission_ask", {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(self._redis_url)
        try:
            result = await redis_client.blpop(f"perm_answer:{request_id}", timeout=60)
            if result is None:
                return "deny"
            return result[1].decode() if isinstance(result[1], bytes) else str(result[1])
        finally:
            await redis_client.aclose()
```

- [ ] **Step 2: Rewrite permission_handler**

```python
# executor_v2/hooks/builtin/permission.py
from __future__ import annotations

import uuid

AUTO_ALLOW = frozenset({"Read", "Grep", "Glob", "Ls"})


async def permission_handler(payload: dict) -> dict:
    tool_name = payload.get("tool_name", "")

    if tool_name in AUTO_ALLOW:
        return {"continue_": True}

    callback = payload.get("_callback")
    if callback is None:
        return {"continue_": True}

    request_id = str(uuid.uuid4())
    decision = await callback.permission_ask(
        request_id=request_id,
        tool_name=tool_name,
        tool_input=payload.get("tool_input", {}),
    )

    if decision == "allow":
        return {"continue_": True}
    return {"continue_": False, "decision": "deny", "reason": f"User denied {tool_name}"}
```

- [ ] **Step 3: Inject callback reference into hook payload**

In `executor_v2/hooks/sdk_bridge.py`, ensure `_callback` is available in the payload passed to hooks. Check how `pre_tool_use` payloads are constructed and add `_callback` reference.

- [ ] **Step 4: Change permission_mode in runtime**

In `executor_v2/runtime.py` `_build_options()`, change:

```python
            permission_mode="default",  # was "acceptEdits" — now hooks control permissions
```

- [ ] **Step 5: Build and test**

```bash
docker compose build backend
docker compose up -d backend --force-recreate
# Submit a task that uses Write/Edit tools
# Verify SSE sends permission_ask event
# Answer via API: POST /sessions/{id}/permission-answer
# Verify executor continues
```

- [ ] **Step 6: Commit**

```bash
git add executor_v2/hooks/builtin/permission.py executor_v2/callbacks.py executor_v2/runtime.py
git commit -m "feat(permission): interactive tool approval via Redis BLPOP"
```

---

### Task 6: SDK Client Pool (#9)

**Problem:** Each run creates a new SDK client. For short tasks or multi-turn conversations, this is wasteful.

**Design decision:** Given that executor_v2 runs as a subprocess (one process per run), a connection pool within the subprocess has limited benefit — the process dies after the run completes. The real optimization is reusing the Claude CLI process across runs in the same session.

**Revised approach:** Instead of a full pool, implement session-level SDK resume:

- [ ] **Step 1: Enable SDK session resume**

The `ClaudeAgentOptions` already has a `resume` parameter. In `runtime.py`, ensure `resume=session_id` is set for all runs (not just checkpoint recovery):

```python
        resume_id = self._config.session_id  # always resume within session
```

This allows the SDK to reuse conversation context across runs in the same session.

- [ ] **Step 2: Commit**

```bash
git add executor_v2/runtime.py
git commit -m "feat(sdk): enable session-level SDK resume for context reuse"
```

---

## Batch C: Integration

### Task 7: IM Gateway Integration (#14)

**Files:**
- Modify: `backend/app/services/callback_service.py`
- Modify: `backend/app/services/im_feishu.py` (if needed)

- [ ] **Step 1: Verify IM callback chain**

Read `callback_service.py` `_handle_run_complete()` to verify it checks `session.im_channel` and sends the reply.

- [ ] **Step 2: Test Feishu flow end-to-end**

```bash
# Simulate a Feishu webhook triggering a task
curl -X POST http://localhost:8080/api/v1/im/feishu/webhook \
  -H "Content-Type: application/json" \
  -d '{"event": {"message": {"content": "帮我查一下天气"}}}'
# Verify: task created → executor runs → callback → IM reply sent
```

- [ ] **Step 3: Fix any gaps found**

Common gaps:
- `im_chat_id` not propagated from session to callback
- Feishu reply formatting (markdown → Feishu card)
- Error replies for failed runs

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/callback_service.py backend/app/services/im_feishu.py
git commit -m "fix(im): verify and fix Feishu → executor_v2 → reply pipeline"
```

---

## Post-Implementation

After all 7 tasks:
1. `simplify` skill — 3 parallel review agents
2. `project-review:pjr` — lint, build, logic check
3. `git-merge-to-develop` — rebase + merge to develop
4. Playwright E2E — desktop + mobile, test MCP tools, permission dialogs, memory recall
