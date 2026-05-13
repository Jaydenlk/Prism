# Stage 2: Poco Quality Alignment — Design Spec

## Goal
7 new features (tasks 8-14) to reach competitive parity with Poco.

## Acceptance Criteria
- User-installed MCP tools callable by agent
- Dangerous tools show confirmation dialog (not auto-executed)
- Logs never leak API keys, passwords, or tokens
- Feishu message triggers Prism run and gets reply

## Batch Strategy

| Batch | Tasks | Reason |
|-------|-------|--------|
| A (parallel) | #8 Workspace, #12 Prompt, #13 Masking | Independent modules |
| B (after A) | #9 Pool, #10 MCP, #11 Permission | Depend on stable executor pipeline |
| C (after B) | #14 IM Gateway | Needs full pipeline working |

---

## Task 8: Workspace Management

**Problem:** Agent runs in `/tmp`, files scattered, no isolation between sessions.

**Design:**
- Create `/workspace/{session_id}/` directory per session
- `ProcessManager.start_run()` creates dir before spawning executor
- `RunConfig.workspace_path` set to `/workspace/{session_id}/`
- SDK `cwd` points to this directory
- Persist across runs in same session (agent can resume work)
- Volume-mount `/workspace/` in docker-compose for persistence

**Files:** `backend/app/services/process_manager.py`, `executor_v2/config.py`, `docker-compose.yml`

---

## Task 9: SDK Client Pool

**Problem:** Every run creates a new `ClaudeSDKClient`, slow startup (~5s).

**Design:**
- `ClaudeSDKClientPool` in `executor_v2/client_pool.py`
- Cache by `(model, base_url, permission_mode)` fingerprint
- LRU eviction, TTL 300s, max 10 entries
- `async with pool.lease(config) as client:` — async context manager
- Health check: verify client can connect before returning from cache
- Singleton pool per executor process (ProcessManager holds reference)

**Reference:** Poco `executor/app/core/client_pool.py`

**Files:** `executor_v2/client_pool.py` (new), `executor_v2/runtime.py`, `executor_v2/__main__.py`

---

## Task 10: MCP Server Injection

**Problem:** User-installed MCP servers not passed to agent SDK.

**Design:**
- `ProcessManager` queries `mcp_servers` table for user's enabled MCP configs
- Pass MCP config as CLI arg or env to executor subprocess
- `executor_v2/__main__.py` parses MCP config → builds `mcpServers` dict for `ClaudeAgentOptions`
- Support stdio transport (command + args) and SSE transport (url)
- MCP lifecycle tied to agent run (start with run, stop with run)

**Reference:** Poco `executor/app/core/channel_runtime.py`

**Files:** `backend/app/services/process_manager.py`, `executor_v2/__main__.py`, `executor_v2/runtime.py`

---

## Task 11: Interactive Permissions

**Problem:** `acceptEdits` mode auto-approves everything, no user control.

**Design:**
- SDK `permission_mode` set to `default` (asks for permission)
- `PreToolUse` hook intercepts tool requests
- Allowlist: `Read`, `Grep`, `Glob` → auto-approve
- Everything else → `callback.permission_ask(tool_name, tool_input)` → SSE to frontend
- Frontend renders approval dialog with tool details
- User clicks approve/deny → `POST /sessions/{id}/permission-answer`
- Backend `RPUSH perm_answer:{request_id}` → executor `BLPOP` with 60s timeout
- Timeout → deny

**Reference:** Poco `executor/app/core/user_input.py` (polling), Prism ADR-028 (BLPOP)

**Files:** `executor_v2/hooks/builtin/permission.py`, `executor_v2/callbacks.py`, `executor_v2/runtime.py`

---

## Task 12: Prompt Composition

**Problem:** System prompt is a manual `"\n\n".join()` of 2 segments.

**Design:**
- `PromptAssembler` class in `executor_v2/prompt.py`
- Ordered segments:
  1. `base` — agent role definition (from agent_type config)
  2. `workspace` — current directory listing (top-level, max 20 items)
  3. `memories` — recall results formatted as bullet list
  4. `skill` — matched skill's system_prompt_addition
  5. `constraints` — user-level constraints from session config
- Each segment has a label header (e.g. `## Workspace Context`)
- `assemble() -> str` produces final prompt
- Replace inline assembly in `__main__.py`

**Files:** `executor_v2/prompt.py` (new), `executor_v2/__main__.py`

---

## Task 13: Log Secret Masking

**Problem:** API keys, passwords visible in logs and callback payloads.

**Design:**
- `SecretMasker` class in `executor_v2/masking.py`
- Patterns: `sk-[A-Za-z0-9]{20,}`, `Bearer [A-Za-z0-9._-]+`, env var values for `*_KEY`, `*_SECRET`, `*_PASSWORD`
- Inject as structlog processor (catches all log output)
- Also mask callback HTTP body before sending
- Deploy in both executor_v2 and backend

**Files:** `executor_v2/masking.py` (new), `executor_v2/callbacks.py`, `backend/app/observability/logging.py`

---

## Task 14: IM Gateway Integration

**Problem:** Old executor's IM hooks not migrated to executor_v2.

**Design:**
- Executor_v2 does NOT handle IM directly (process boundary)
- Backend's `_handle_run_complete` already checks `session.im_channel`
- Need to verify: Feishu webhook → `POST /tasks` flow works with executor_v2
- Need to verify: `run_complete` callback → IM gateway → Feishu reply
- Fix any gaps in the callback chain (e.g. missing `im_chat_id` propagation)

**Files:** `backend/app/services/callback_service.py`, `backend/app/services/im_feishu.py`
