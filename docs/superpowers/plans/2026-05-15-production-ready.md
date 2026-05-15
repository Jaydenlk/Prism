# Prism v2 Production-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Prism v2 market-viable — every feature works end-to-end, beats Poco on UX, passes all quality gates.

**Architecture:** Bottom-up verification with parallel independent fixes. Group 1 (nginx/IDOR/frontend build) runs in parallel. Group 2 (Docker rebuild + E2E smoke) is the serial gate. Group 3 (feature verification) runs in parallel after Group 2 passes. Group 4 (quality) runs last.

**Tech Stack:** Python 3.12, FastAPI, claude-agent-sdk 0.1.50 (bundles CLI), React 18 + TypeScript + Vite, PostgreSQL 16 (pgvector), Redis 7, nginx 1.27, Docker Compose, Playwright

**Spec:** Brainstorming diagnosis in current conversation (2026-05-15). Master Spec at `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `docker-compose.yml` | Modify line 187 | Mount `frontend-react/dist` instead of `frontend/` |
| `nginx/nginx.conf` | Rewrite | React SPA routing (`index.html`, catch-all fallback) |
| `backend/app/services/memory_service.py` | Modify | IDOR fix: delete verifies ownership |
| `frontend-react/` | Build | `npm ci && npm run build` to produce `dist/` |

---

## Group 1: Independent Fixes (parallel, no dependencies)

### Task 1: nginx → serve React frontend

**Files:**
- Modify: `docker-compose.yml:187`
- Rewrite: `nginx/nginx.conf`

- [ ] Change docker-compose volume mount from old frontend to React dist:

```yaml
# docker-compose.yml line 187 — change:
      - ./frontend:/usr/share/nginx/prism-frontend:ro
# to:
      - ./frontend-react/dist:/usr/share/nginx/prism-frontend:ro
```

- [ ] Rewrite nginx.conf for React SPA routing:

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    # Health endpoint (no backend round-trip)
    location = /healthz {
        access_log off;
        add_header Content-Type text/plain;
        return 200 "ok\n";
    }

    # SSE stream passthrough (ADR-115)
    location ~ ^/api/v1/sessions/[^/]+/stream {
        proxy_pass         http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header   Connection "";
        proxy_buffering    off;
        proxy_cache        off;
        proxy_set_header   X-Accel-Buffering no;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding off;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # API + backend endpoints
    location ~ ^/(api|health|metrics|docs|redoc|openapi\.json) {
        proxy_pass         http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
    }

    # React SPA — static assets + client-side routing fallback
    root /usr/share/nginx/prism-frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
        add_header X-Content-Type-Options  "nosniff"       always;
        add_header X-Frame-Options         "DENY"           always;
        add_header X-XSS-Protection        "1; mode=block"  always;
        add_header Referrer-Policy         "strict-origin-when-cross-origin" always;
    }
}
```

Key changes from old config:
- `index.html` instead of `Prism.html`
- `try_files $uri $uri/ /index.html` — SPA catch-all for React Router
- Removed separate regex for static assets (Vite hashes filenames, `try_files` handles it)
- Removed `/auth/magic` and `/auth/complete-signup` special routes (SPA fallback covers them)

- [ ] Verify syntax: `nginx -t` (inside container after rebuild)

- [ ] Commit: `fix(nginx): serve React SPA from frontend-react/dist`

---

### Task 2: Fix Memory IDOR vulnerability

**Files:**
- Modify: `backend/app/services/memory_service.py:104-113`

- [ ] Add ownership verification before delete — the `delete_memory` method accepts `user_id` but doesn't verify the memory belongs to that user:

```python
async def delete_memory(self, user_id: str, memory_id: str) -> None:
    self._require_enabled()
    mem = _get_memory()
    owned = await self.list_memories(user_id)
    owned_ids = {m.get("id") for m in owned}
    if memory_id not in owned_ids:
        raise HTTPException(status_code=404, detail="Memory not found")
    try:
        await mem.delete(memory_id=memory_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("memory.delete_error", memory_id=memory_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Memory delete failed")
```

- [ ] Verify syntax: `python -c "import py_compile; py_compile.compile('backend/app/services/memory_service.py', doraise=True)"`

- [ ] Commit: `fix(memory): IDOR — delete verifies ownership before removing`

---

### Task 3: Rebuild frontend-react

**Files:**
- Build: `frontend-react/`

- [ ] Install dependencies and build:

```bash
cd frontend-react
npm ci
npm run build
```

Expected: `dist/` directory with `index.html` and hashed JS/CSS chunks.

- [ ] Verify build output:

```bash
ls frontend-react/dist/index.html
```

Expected: file exists.

- [ ] Verify TypeScript strict mode passes (build script runs `tsc` before Vite):

If build fails, fix TypeScript errors before proceeding. The `tsc && vite build` pipeline in `package.json` ensures type safety.

- [ ] Commit built assets are NOT committed (dist/ should be in .gitignore). Only source changes get committed.

---

## Group 2: Foundation Verification (serial, depends on Group 1)

### Task 4: Docker rebuild + executor_v2 end-to-end smoke test

**Files:**
- No code changes — this is a verification task
- If issues found, fix inline and document

**Pre-condition:** Tasks 1-3 complete (nginx config updated, IDOR fixed, frontend built)

- [ ] Rebuild Docker images:

```bash
docker compose build --no-cache backend
docker compose up -d
```

- [ ] Wait for all services healthy:

```bash
docker compose ps
```

Expected: postgres, redis, backend, searxng, nginx all `healthy`.

- [ ] Verify nginx serves React frontend:

```bash
curl -s http://localhost/index.html | head -5
```

Expected: HTML with React app root div.

- [ ] Login and get JWT:

```bash
curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@prism.dev","password":"PrismAdmin!2026"}' \
  | python -m json.tool
```

Expected: `{"data": {"access_token": "...", ...}}`. Save the token.

- [ ] Create a session:

```bash
TOKEN="<from above>"
curl -s -X POST http://localhost/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"smoke-test"}' \
  | python -m json.tool
```

Expected: `{"data": {"id": "<session_id>", ...}}`. Save the session_id.

- [ ] Submit a simple task (non-tool-use):

```bash
SESSION_ID="<from above>"
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"Hello, say hi back in one sentence.\"}" \
  | python -m json.tool
```

Expected: 202 with `run_id`.

- [ ] Check backend logs for executor_v2 startup:

```bash
docker compose logs backend --tail 50
```

Expected: `executor_v2.starting`, `sdk_connected`, no `CLINotFoundError`, no import errors.

- [ ] Check run completes (poll or SSE):

```bash
RUN_ID="<from above>"
curl -s http://localhost/api/v1/runs/$RUN_ID \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool
```

Expected: `status: "completed"`, `output_tokens > 0`.

- [ ] **If executor_v2 fails:** Read stderr from docker logs, identify root cause, fix, and repeat. Common failures:
  - `CLINotFoundError` → SDK bundled CLI missing in container. Fix: add `RUN pip install claude-agent-sdk[cli]` or ensure `_bundled/claude` exists in pip package.
  - Import errors → Missing dependency in `backend/requirements.txt`. Fix: add missing package.
  - DB query errors → `config.py` SQL doesn't match current schema. Fix: align query with actual columns.
  - API key errors → Provider not configured or key not set. Fix: configure via admin UI or `.env`.

- [ ] Submit a tool-use task (the real test):

```bash
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"List the files in the /workspace directory using the Bash tool.\"}"
```

Expected: Run completes, callback events include `tool_start` + `tool_end` + `message_complete`.

- [ ] Verify SSE streaming works:

Open a browser to `http://localhost`, login, open the smoke-test session, send a message. Verify text streams in real-time (not all-at-once after completion).

- [ ] Document any fixes made. Commit: `fix(docker): executor_v2 end-to-end verified`

---

## Group 3: Feature Verification (parallel, depends on Group 2)

### Task 5: Memory end-to-end verification

**Pre-condition:** executor_v2 runs successfully (Task 4 passed)

- [ ] Add a memory via API:

```bash
curl -s -X POST http://localhost/api/v1/memories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"I live in Shanghai and prefer window seats on trains."}'
```

Expected: 201.

- [ ] List memories:

```bash
curl -s http://localhost/api/v1/memories \
  -H "Authorization: Bearer $TOKEN"
```

Expected: Contains the memory just added.

- [ ] Submit a task that should trigger memory recall:

```bash
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"Help me find a high-speed train ticket for next week.\"}"
```

Expected: Agent response mentions Shanghai (recalled from memory) without user specifying it.

- [ ] Verify IDOR protection — create a second user, try to delete first user's memory:

```bash
# This should return 404, not delete the memory
curl -s -X DELETE http://localhost/api/v1/memories/<memory_id_of_user_1> \
  -H "Authorization: Bearer $TOKEN_USER_2"
```

Expected: 404 "Memory not found".

- [ ] Search memories:

```bash
curl -s "http://localhost/api/v1/memories/search?q=shanghai" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: Returns the Shanghai memory.

- [ ] If any failure: fix and commit. Document in HANDOFF-LOG.

---

### Task 6: Intent Router + Skills verification

**Pre-condition:** executor_v2 runs (Task 4)

- [ ] Submit a memo-type prompt:

```bash
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"Help me remember: meeting with Alice tomorrow at 3pm.\"}"
```

Check backend logs for `intent.classified category=memo`.

- [ ] Submit a research-type prompt:

```bash
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"Research the latest developments in AI agent frameworks and give me a summary.\"}"
```

Check backend logs for `intent.classified category=research`.

- [ ] Submit a brainstorm-type prompt:

```bash
curl -s -X POST http://localhost/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"prompt\":\"Let's brainstorm ideas for a productivity app for students.\"}"
```

Check backend logs for `intent.classified category=brainstorm`.

- [ ] If routing is wrong or skill prompt not injected: fix IntentRouter/RouterHook and commit.

---

### Task 7: IM Gateway fixes

**Pre-condition:** Backend running (Task 4)

**Files:**
- Investigate: `backend/app/services/im_feishu.py`
- Fix: asyncio event loop conflict

- [ ] Read the Feishu adapter's WebSocket code. The error was `this event loop is already running`. Likely caused by calling `asyncio.run()` or creating a new event loop inside an already-running async context.

- [ ] Fix: Use `asyncio.create_task()` or `await` instead of `asyncio.run()` / `loop.run_until_complete()` within the async context.

- [ ] Verify all IM webhook endpoints respond:

```bash
# Feishu URL verification
curl -s -X POST http://localhost/api/v1/im/webhook/feishu \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test123"}'

# WeCom URL verification (GET)
curl -s "http://localhost/api/v1/im/webhook/wecom?msg_signature=test&timestamp=123&nonce=abc&echostr=hello"
```

- [ ] Commit: `fix(im): Feishu WebSocket asyncio event loop conflict`

---

## Group 4: Quality Gates (serial, depends on Group 3)

### Task 8: Simplify review

**Skill:** `simplify`

- [ ] Load the `simplify` skill
- [ ] Run 3-subagent parallel review: reuse / quality / efficiency
- [ ] Fix all findings
- [ ] Commit fixes

---

### Task 9: PJR (lint + build + logic)

**Skill:** `project-review:pjr`

- [ ] Load PJR skill

- [ ] Backend lint:

```bash
cd backend && python -m py_compile app/main.py
ruff check .
```

- [ ] Frontend lint + build:

```bash
cd frontend-react
npx eslint src/ --max-warnings 0
npx tsc --noEmit
npm run build
```

- [ ] Fix all errors. Commit.

---

### Task 10: Merge to develop

**Skill:** `git-merge-to-develop:git-merge-to-develop`

- [ ] Load git-merge-to-develop skill
- [ ] Rebase on develop
- [ ] Resolve conflicts
- [ ] Merge

---

### Task 11: E2E Playwright testing

**Tool:** Playwright MCP (browser automation)

**Viewports:** Desktop (1280×800) + Mobile (390×844)

- [ ] **Login flow:**
  - Navigate to `http://localhost`
  - Verify login page renders
  - Enter credentials (admin@prism.dev / PrismAdmin!2026)
  - Click login
  - Verify redirect to chat page
  - Verify session list loads

- [ ] **Chat flow:**
  - Create new session
  - Type a message and send
  - Verify SSE streaming (text appears incrementally)
  - Verify tool call card appears (if tool used)
  - Verify message complete renders with markdown

- [ ] **Memory flow:**
  - Navigate to Settings → Memory tab
  - Add a memory
  - Verify it appears in list
  - Search for it
  - Delete it
  - Verify ownership (another user can't see it)

- [ ] **Skills Market:**
  - Navigate to Skills Market
  - Search for a skill
  - Verify results appear
  - Install a skill (if marketplace configured)
  - Verify install completes

- [ ] **Settings:**
  - Navigate to Settings
  - Switch provider
  - Verify provider test endpoint works
  - Toggle dark mode
  - Verify UI updates

- [ ] **Admin:**
  - Navigate to Admin panel
  - Verify user list
  - Verify invite code management
  - Verify usage dashboard

- [ ] **Mobile viewport (390×844):**
  - Repeat login + chat + memory flows
  - Verify responsive layout
  - Verify mobile menu/sidebar

- [ ] **Edge cases:**
  - Empty session list
  - Very long message
  - Network disconnect → reconnect
  - Invalid token → redirect to login

- [ ] Document all findings. Fix any bugs found. Commit.

---

## Verification Criteria

- [ ] executor_v2 completes a multi-turn tool-calling task without crash
- [ ] SSE streaming works in frontend (text appears incrementally)
- [ ] Memory: add → recall in next prompt → delete with IDOR protection
- [ ] Intent Router: 3+ categories correctly classified
- [ ] nginx serves React frontend (not old Prism.html)
- [ ] Frontend build: `tsc --noEmit` zero errors, `npm run build` succeeds
- [ ] Backend: `ruff check .` zero errors
- [ ] Playwright E2E: login → chat → memory → skills → settings (desktop + mobile)
- [ ] All IM webhooks respond correctly
- [ ] Docker `docker compose ps` — all services healthy
