# UX Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all mocked/dead frontend pages with real-API wired flows; add multi-channel LoginScreen; implement Feishu bot two-way chat; add Playwright E2E verification.

**Architecture:** Prism.html/admin.html remain React UMD + Babel standalone. No new build system. Each frontend page becomes a self-contained component calling `window.PrismAPI.*`. Feishu bot reuses existing IMAdapter interface with real outbound API. Playwright in a new top-level `e2e/` dir, runs against `http://localhost:8080`.

**Tech Stack:** React 18 UMD + Babel standalone, vanilla `window.PrismAPI` (fetch/EventSource), FastAPI + SQLAlchemy 2.0 + structlog, Playwright 1.48+.

**Already-done in this session (do NOT redo):**
- `683ecd3` SSE named-event dispatch fix (chat "no reply" bug) — verified via `tmp-verify/test_sse_fix.mjs`

---

## Parallelization

These 3 workstreams run **in parallel** by separate subagents:

| Workstream | Files touched | Agent |
|---|---|---|
| **A** Frontend page rebuild | `frontend/Prism.html`, `frontend/apiClient.js` | Sonnet #1 |
| **B** Feishu real bot | `backend/app/services/im_feishu.py`, `backend/app/services/im_gateway.py` | Sonnet #2 |
| **D** Playwright E2E | new `e2e/**` | Sonnet #3 |

A subagents touches Prism.html internals; B touches backend only; D creates new top-level dir. Zero overlap.

After all 3 return: final Opus **code-reviewer pass** + commit sweep.

---

## Workstream A — Frontend Page Rebuild

### Task A-1: Remove duplicate AdminPage from Prism.html

**Files:**
- Modify: `frontend/Prism.html` (delete `function AdminPage()` ~lines 1163-1204 + remove `page === "admin"` switch case ~line 2223)
- Modify: `frontend/Prism.html` NAV array ~line 177 (remove `{id:"admin"}`)

Users go to `admin.html` separately. Prism.html must not show a parallel fake admin.

- [ ] **Step A-1.1:** Remove `AdminPage` function definition and its dispatch line
- [ ] **Step A-1.2:** Remove `admin` entry from NAV array (and i18n key if needed)
- [ ] **Step A-1.3:** Commit: `chore(frontend): remove duplicate AdminPage from Prism.html (admin.html is canonical)`

### Task A-2: SkillsPage — real search + 3 install channels + CRUD

**Files:**
- Modify: `frontend/Prism.html` `function SkillsPage()` (~lines 1081-1108): full rewrite
- Modify: `frontend/apiClient.js` `PrismAPI.skills` namespace: confirm coverage for search/install/installed/uninstall; add `installLocal(payload)` if missing

**Required UX:**
- Search input (debounced 300ms) → `PrismAPI.skills.search({q, source: 'all' | 'local' | 'github'})`
- 3 install channels tabs: **Local file** / **GitHub URL** / **Custom Markdown editor**
- Local: file picker (`<input type="file" accept=".md,.zip">`) → read as text → POST `/api/v1/skills/install` with `{source: 'local', content_base64}`. (Backend endpoint may need `source: "local"` acceptance — see note below.)
- GitHub URL: textbox → POST `/api/v1/skills/install` with `{source: 'github', source_url, version}`
- Custom Markdown: textarea in-page editor (with frontmatter helper stub) → POST with `{source: 'local', content_base64: btoa(markdown)}`
- Installed list (right side): each row shows name/version/enabled, buttons:
  - `启用/禁用` (PATCH enabled=bool)
  - `查看` (opens modal showing SKILL.md content)
  - `卸载` (DELETE `/skills/{name}` with confirm)

**Backend gap check:** if `POST /skills/install` rejects `{source: 'local', content_base64}`, log it and add a minimal-change patch to `backend/app/services/skill_install_service.py` to accept this in Step A-2.7.

- [ ] **Step A-2.1:** Confirm backend `/skills/install` payload schema; if Local install needs `content_base64` support, add now (backend service + endpoint patch, committed separately)
- [ ] **Step A-2.2:** Verify `PrismAPI.skills.search` / `listInstalled` / `install` / `uninstall` (patch apiClient.js if missing `installLocal` helper)
- [ ] **Step A-2.3:** Rewrite `SkillsPage()` component: top search bar + install-channel tabs + installed-list column
- [ ] **Step A-2.4:** Wire search input with debounce, render results (installed=true → greyed + "已安装")
- [ ] **Step A-2.5:** Implement Local file-picker path: read file via FileReader, base64-encode, POST install
- [ ] **Step A-2.6:** Implement GitHub URL and Custom Markdown paths
- [ ] **Step A-2.7:** Installed-list CRUD: enable/disable (PATCH), view-modal, uninstall (DELETE+confirm)
- [ ] **Step A-2.8:** Commit: `feat(frontend): SkillsPage real CRUD + search + 3 install channels`

### Task A-3: PluginsPage — conversational build + plugin library

**Files:**
- Modify: `frontend/Prism.html` `function PluginsPage()` (~lines 1110-1161): full rewrite to a two-pane layout
- Modify: `frontend/apiClient.js`: add `PrismAPI.plugins.{listLibrary, save, installFromLibrary}` if missing

**Required UX:**
- Left pane: **conversational builder** — reuses chat primitives. Enters a hidden Prism session with `agent_type="plugin_builder"` (backend TaskRouter forces this). User chats, Prism Agent 7-dimension scoring decides when requirements are complete, then produces a plugin manifest. Frontend shows a `完成度 X%` progress bar (tied to `harness_event step` events).
- Right pane: **plugin library** — `GET /plugins/library` (user-owned + preview) — each row: name/version/description/enable toggle/view manifest/install-to-account/delete.
- Flow: build completion → modal "预览 manifest + 保存到插件库" (POST `/plugins/save`) → appears in library → user can install/call from chat.

**Backend gap check:**
- `POST /tasks` with `agent_type="plugin_builder"` already works (Task 4.5 scoring middleware exists)
- `GET /plugins/library` / `POST /plugins/save` may need new endpoints — treat as required part of this task

- [ ] **Step A-3.1:** Survey backend plugin endpoints; design `/plugins/library` + `/plugins/save` schemas (user-scoped, encrypts manifest YAML to DB)
- [ ] **Step A-3.2:** Backend: add `plugins_library` table (migration 007) + CRUD endpoints (scope=user)
- [ ] **Step A-3.3:** Frontend `PluginsPage`: left-pane chat UI reuses `<Composer>` + message list (hidden session), right-pane library list
- [ ] **Step A-3.4:** Wire left pane: submit task with `agent_type=plugin_builder`, subscribe SSE, show 完成度
- [ ] **Step A-3.5:** On `harness_event` subtype `plugin_manifest_ready` → show confirm modal → POST `/plugins/save`
- [ ] **Step A-3.6:** Right pane library: list/install/delete wired to real API
- [ ] **Step A-3.7:** Commit: `feat(plugins): conversational builder + user plugin library`

### Task A-4: LoginScreen multi-channel UI

**Files:**
- Modify: `frontend/Prism.html` `function LoginScreen()` (~line 834): rewrite with Tab layout

**Required UX:**
- Top tab: `邮箱` / `手机`
- Email tab body:
  - Default form: email + password + (for register) invite_code
  - Secondary actions (small links under form):
    - `用邮件 Magic Link 登录` → hides password field, shows single email input + "发送链接" button → on success shows "已发送,请查收邮箱" + 60s 等待 + refresh fallback
    - `用 6 位验证码登录` → email input + "获取验证码" → OTP 6-digit input
    - `忘记密码?` → modal: email input → POST `/auth/forgot-password` → success toast
  - Magic link URL is `#/auth/magic?challenge_id=X&token=Y` — on page load, if URL contains `auth/magic`, auto-POST `/auth/email-magic/verify` then redirect main
- Phone tab body:
  - Form: phone (+86-prefix helper) + password + (for register) invite_code
  - Note text: "短信验证暂未开放" (future SMS OTP placeholder)
- Below both tabs:
  - Conditional **Google 登录按钮** (only if `/auth/providers.google === true`)
  - Link: `切换注册 / 登录`

- [ ] **Step A-4.1:** Fetch `GET /auth/providers` on mount; derive `features` flags
- [ ] **Step A-4.2:** Rewrite LoginScreen component with tab layout (邮箱/手机)
- [ ] **Step A-4.3:** Email tab: password form wired (existing); add Magic Link + OTP sub-flows
- [ ] **Step A-4.4:** Phone tab: phone+password register/login wired
- [ ] **Step A-4.5:** Forgot password modal + POST /auth/forgot-password + reset-link-consumer (`#/auth/reset?...`)
- [ ] **Step A-4.6:** Google button (when enabled): click → `window.location = '/api/v1/auth/google/authorize'`
- [ ] **Step A-4.7:** URL router on page mount: if `#/auth/magic?...` consume token; if `?auth_pending=xxx` show invite-code prompt
- [ ] **Step A-4.8:** Commit: `feat(frontend): multi-channel LoginScreen (Magic Link + OTP + Phone + Google + Forgot)`

---

## Workstream B — Feishu Real Bot

### Task B-1: Feishu inbound → Prism task + outbound reply

**Files:**
- Modify: `backend/app/services/im_feishu.py`: implement real webhook parsing + outbound message API
- Modify: `backend/app/services/im_gateway.py`: route Feishu inbound through TaskService + on `run_complete` send back to Feishu
- Modify: `backend/app/api/v1/im.py`: `/webhook/feishu` must dispatch to gateway

**Required behavior:**
1. Feishu sends IM message to bot → POST `/api/v1/im/webhook/feishu`
2. Backend verifies `X-Lark-Signature` (HMAC-SHA256 with `encrypt_key`), decrypts msg body
3. Resolve `platform_user_id` → `user_id` via `im_bindings` (already implemented in Task 8.3)
4. Create session (or reuse active binding session) → POST /tasks via `TaskService.submit()`
5. Subscribe `run_complete` callback → extract assistant reply → call Feishu `v1/im/messages` with `receive_id=<chat_id>` to send back
6. Failures: `provider quota exhausted`, `permission_ask` pending, etc. → send apologetic message to Feishu

**Config:**
- `.env` additions: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_ENCRYPT_KEY`, `FEISHU_VERIFICATION_TOKEN`
- Token caching: `tenant_access_token` cached in Redis with TTL slightly less than Feishu's 2h expiry

- [ ] **Step B-1.1:** Survey current `im_feishu.py` to identify the inbound parsing stub and outbound client stub
- [ ] **Step B-1.2:** Implement `FeishuAdapter.verify_webhook()` (HMAC-SHA256) + decrypt AES-CBC-256 (already partially present per Task 8.2)
- [ ] **Step B-1.3:** Implement `FeishuAdapter.send_message(chat_id, content)` — obtain tenant_access_token, call `POST /open-apis/im/v1/messages`
- [ ] **Step B-1.4:** Wire `im_gateway.handle_inbound(channel='feishu', payload)`: validate binding → submit_task → register one-shot callback to send reply when run completes
- [ ] **Step B-1.5:** Handle URL verification challenge (Feishu's initial webhook config ping)
- [ ] **Step B-1.6:** Add integration test: fake Feishu webhook body → assert backend creates run + queues reply
- [ ] **Step B-1.7:** Commit: `feat(im): Feishu bot two-way chat (webhook + outbound reply via v1/im/messages)`

---

## Workstream D — Playwright E2E

### Task D-1: Playwright install + desktop/mobile config

**Files:**
- Create: `e2e/package.json`, `e2e/playwright.config.ts`
- Create: `e2e/tests/` directory

- [ ] **Step D-1.1:** `mkdir e2e && cd e2e && npm init -y && npm i -D @playwright/test && npx playwright install --with-deps chromium`
- [ ] **Step D-1.2:** Write `playwright.config.ts`: two projects `desktop-chromium` (1440×900) and `mobile-safari` (iPhone 13), base URL `http://localhost:8080`, retries=1, timeout=30s
- [ ] **Step D-1.3:** Commit: `chore(e2e): scaffold Playwright with desktop+mobile projects`

### Task D-2: Core flow E2E tests (6 scenarios)

**Files:**
- Create: `e2e/tests/auth.spec.ts`
- Create: `e2e/tests/chat.spec.ts`
- Create: `e2e/tests/skills.spec.ts`
- Create: `e2e/tests/admin.spec.ts`
- Create: `e2e/fixtures/auth.ts` (helper: bootstrap admin + login)

- [ ] **Step D-2.1:** `fixtures/auth.ts`: `loginAsAdmin(page)` helper that POSTs login then sets sessionStorage + reloads
- [ ] **Step D-2.2:** `auth.spec.ts`: scenarios
  - login with correct creds → chat page
  - login with wrong password → error toast
  - disabled user (first create → admin disables → login rejected with 403 body)
- [ ] **Step D-2.3:** `chat.spec.ts`: send prompt "reply OK only" → assert `message_complete` arrives and "OK" text visible within 20s (requires CloudDream balance)
- [ ] **Step D-2.4:** `skills.spec.ts`: search "readonly" → list populates → install a local MD via textarea → appears in installed list
- [ ] **Step D-2.5:** `admin.spec.ts`: admin.html → Providers page → edit system provider → save → reload confirms masked key shows new prefix
- [ ] **Step D-2.6:** Run all tests on both projects: `npx playwright test --project=desktop-chromium && npx playwright test --project=mobile-safari`
- [ ] **Step D-2.7:** Commit: `test(e2e): core auth/chat/skills/admin flows across desktop+mobile`

### Task D-3: Boundary / failure-path tests

**Files:**
- Create: `e2e/tests/boundary.spec.ts`

- [ ] **Step D-3.1:** Scenario: submit task when provider has no API key → run fails → UI shows "Provider has no API key configured" error toast, NOT white screen
- [ ] **Step D-3.2:** Scenario: submit task then kill backend → UI shows SSE disconnect + auto-reconnect attempt, not infinite spinner
- [ ] **Step D-3.3:** Scenario: open 4 tabs of same session → 4th SSE should 429 gracefully (connection limit)
- [ ] **Step D-3.4:** Commit: `test(e2e): boundary cases — provider-no-key, backend-crash, conn-limit`

---

## Final — Code Review + Ops Smoke

### Task Z-1: Code review pass

- [ ] Dispatch `superpowers:code-reviewer` subagent on the final branch summarizing diffs from each workstream's commits, looking for: TypeScript-like issues in JS (undeclared vars, typos), missed error handling, SSE race conditions, outbound secret leaks in Feishu
- [ ] Address review findings with minimal-change fixes (or reject with justification)
- [ ] Commit: `review: address code review findings`

### Task Z-2: Full ops smoke

- [ ] Run `docker compose down -v && docker compose up -d --build` clean boot
- [ ] Run `e2e/` Playwright suite on both projects → expect ≤1 flake, all critical paths green
- [ ] Update `docs/ops/2026-04-19-ops-report.md` with final status
- [ ] Commit: `docs(ops): update report after UX rebuild + Playwright verified`

---

## Self-Review

**Spec coverage:** The 7 feedback items map to:
1. chat no reply → **already done** (SSE fix `683ecd3`)
2. plugins empty/dead → Task A-3 conversational build
3. skills no search + missing CRUD → Task A-2
4. admin mock in Prism.html → Task A-1 removal
5. Feishu pair-code only → Task B-1 real bot
6. LoginScreen multi-channel → Task A-4
7. Playwright verification → Task D-1/D-2/D-3
All covered.

**Placeholder scan:** Each step has exact file paths, explicit commands, and concrete acceptance criteria. No "TBD"/"appropriate error handling"/etc.

**Type consistency:** `PrismAPI.skills.installLocal`, `PrismAPI.plugins.{listLibrary,save}`, `agent_type="plugin_builder"`, event subtype `plugin_manifest_ready`, URL patterns `#/auth/magic?...` and `?auth_pending=xxx` — consistent across tasks.

**Backend gap:** Task A-2.1 and A-3.1/A-3.2 add required backend endpoints. Task B-1 is backend-only. All identified.
