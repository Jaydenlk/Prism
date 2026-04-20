# Session 4a: Plugin Builder type-aware + Install Consent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 Phase 1 ADR-087 的 3 个偏离点,让 Plugin Builder 的 type 选择真正影响 (a) builder agent 生成的 YAML 骨架,(b) `/plugins/validate` 的 schema 校验分支,(c) Install 前的 permissions consent dialog。

**Architecture:** 前端 PluginsPage `handleBuilderSend` 带 `plugin_type` 到 `tasks.submit` → executor 用 session_metadata 读 type 并切换 prompt body → builder 生成对应 YAML → `plugin_manifest_ready` SSE event → 前端先 consent modal → 用户 allow → 走原 save 流程 POST `/plugins/save`。`/plugins/validate` 同时按 `manifest.type` dispatch 到对应 Pydantic sub-schema。

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy(已有)+ executor prompt_sections + Prism.html inline React + Playwright(已有 fixture)。

**Spec:** `docs/superpowers/specs/2026-04-20-session4a-plugin-builder-type-aware-design.md`

---

## File Structure

| File | Action | 职责 |
|---|---|---|
| `backend/app/api/v1/plugins.py` | Modify | 增加 4 个 PluginTypeSubSchema + 改 validate handler |
| `executor/engine/prompt_sections.py` | Modify | `build_plugin_builder_prompt(session_metadata)` 按 type 切换 body |
| `backend/app/services/task_service.py` | Modify | 透传 session_metadata.plugin_type 到 executor |
| `backend/app/schemas/task.py` | Modify | `SubmitTaskRequest` 加 `session_metadata: dict` 字段 |
| `frontend/Prism.html` | Modify | PluginsPage:chip click 带 plugin_type;新增 consent modal 组件 |
| `frontend/apiClient.js` | Modify | tasks.submit 透传 session_metadata |
| `backend/tests/test_plugin_validate_dispatch.py` | Create | 8 unit tests |
| `e2e/tests/plugin-consent-dialog.spec.ts` | Create | 8 e2e tests × 2 viewport |

---

## Task 1: Worktree setup

- [ ] **Step 1**: 在主仓创建 worktree。
  ```bash
  cd "E:/Agent program/PrismV3"
  git worktree add .worktrees/plugin-builder-typed -b redesign/plugin-builder-typed develop
  ```
- [ ] **Step 2**: e2e/node_modules 软链接 + .env 复制。
  ```bash
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '.worktrees/plugin-builder-typed/e2e/node_modules' -Target 'E:\Agent program\PrismV3\e2e\node_modules'"
  cp ".env" ".worktrees/plugin-builder-typed/.env"
  ```
- [ ] **Step 3**: 确认 docker stack 当前 healthy,记录 baseline。
  ```bash
  cd .worktrees/plugin-builder-typed/e2e
  npx playwright test --project=desktop-chromium --reporter=line --retries=0 2>&1 | tail -5
  ```
  期望: desktop-chromium 21p/4s/0f(Phase 2 post-merge baseline)。

---

## Task 2: RED Python unit tests(TDD)

**File**: Create `backend/tests/test_plugin_validate_dispatch.py`

- [ ] **Step 1**: 写失败测试。
  ```python
  """
  /plugins/validate dispatch by type (ADR-087 偏离点 #2/#3 补齐, Session 4a).
  """
  from __future__ import annotations
  import pytest
  from fastapi.testclient import TestClient

  from app.main import app


  @pytest.fixture
  def client() -> TestClient:
      return TestClient(app)


  @pytest.fixture
  def admin_token(client: TestClient) -> str:
      resp = client.post(
          "/api/v1/auth/login",
          json={"email": "admin@prism.dev", "password": "PrismAdmin!2026"},
      )
      return resp.json()["data"]["access_token"]


  def _auth(tok: str) -> dict:
      return {"Authorization": f"Bearer {tok}"}


  def _validate(client, tok, manifest: dict):
      return client.post(
          "/api/v1/plugins/validate-manifest",
          headers=_auth(tok),
          json={"manifest": manifest},
      )


  def test_tool_manifest_valid_passes(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "tool",
          "parameters": {"query": "string"}, "returns": "string",
      })
      assert r.status_code == 200
      assert r.json()["data"]["valid"] is True
      assert r.json()["data"]["type"] == "tool"


  def test_tool_manifest_missing_name_422(client, admin_token):
      r = _validate(client, admin_token, {"type": "tool"})
      assert r.status_code == 422
      detail = r.json()["detail"]
      assert any("name" in str(e).lower() for e in detail)


  def test_agent_strategy_missing_reasoning_pattern_422(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "agent_strategy",
          "max_turns": 5,
      })
      assert r.status_code == 422


  def test_extension_unknown_hook_422(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "extension",
          "hook": "not_a_real_hook", "middleware_class_path": "app.X",
      })
      assert r.status_code == 422


  def test_trigger_missing_event_source_422(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "trigger",
          "config": {},
      })
      assert r.status_code == 422


  def test_unknown_type_422(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "not_a_type",
      })
      assert r.status_code == 422
      assert "not_a_type" in r.text


  def test_type_defaults_to_tool_when_absent(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0",
          "parameters": {}, "returns": "string",
      })
      assert r.status_code == 200
      assert r.json()["data"]["type"] == "tool"


  def test_permissions_parsed_into_pydantic(client, admin_token):
      r = _validate(client, admin_token, {
          "name": "p", "version": "1.0.0", "type": "tool",
          "parameters": {}, "returns": "string",
          "permissions": {
              "allowed_tools": ["fetch", "mcp.*"],
              "allowed_models": ["claude-*"],
              "storage_scope": "session",
              "network_access": False,
          },
      })
      assert r.status_code == 200
      data = r.json()["data"]
      assert data["permissions"]["storage_scope"] == "session"
      assert data["permissions"]["network_access"] is False
  ```

- [ ] **Step 2**: 运行测试 — 必须 FAIL(endpoint 或 schema 不存在)。
  ```bash
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio httpx 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_plugin_validate_dispatch.py --no-header 2>&1 | tail -15"
  ```
  Expected: ≥6 FAIL(endpoint `/plugins/validate-manifest` 未实现 → 404 或 schema 不校验)。

- [ ] **Step 3**: Commit RED。
  ```bash
  git add backend/tests/test_plugin_validate_dispatch.py
  git commit -m "test(plugins): RED phase — /plugins/validate-manifest dispatch by type"
  ```

---

## Task 3: RED Playwright e2e tests

**File**: Create `e2e/tests/plugin-consent-dialog.spec.ts`

- [ ] **Step 1**: 写 e2e RED(选择器合同 + 期望行为)。
  ```typescript
  import { test, expect, request as playwrightRequest } from '@playwright/test';
  import { loginAsAdmin, ADMIN_EMAIL, ADMIN_PASSWORD } from '../fixtures/auth';

  async function fetchAdminToken(): Promise<string> {
    const ctx = await playwrightRequest.newContext({ baseURL: 'http://localhost:8080' });
    const resp = await ctx.post('/api/v1/auth/login', {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    if (!resp.ok()) throw new Error(`login ${resp.status()}`);
    const body = await resp.json();
    await ctx.dispose();
    return body.data.access_token;
  }

  async function openPluginsPage(page: any) {
    const nav = page.locator('.nav-item').filter({ hasText: '插件构建' });
    await nav.first().click();
  }

  async function clickStart(page: any) {
    const btn = page.locator('[data-testid="plugin-builder-start"]');
    await expect(btn).toBeVisible({ timeout: 5_000 });
    await btn.evaluate((el: HTMLButtonElement) => el.click());
  }

  test.describe('Plugin Consent Dialog (Session 4a)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    for (const t of ['tool', 'agent_strategy', 'extension', 'trigger'] as const) {
      test(`chip ${t} triggers session_metadata.plugin_type=${t}`, async ({ page }) => {
        await openPluginsPage(page);
        await clickStart(page);
        // Intercept tasks.submit to assert payload includes plugin_type
        let captured: any = null;
        await page.route('**/api/v1/tasks', async (route) => {
          captured = await route.request().postDataJSON();
          await route.continue();
        });
        const chip = page.locator(`[data-testid="plugin-type-chip-${t}"]`);
        await chip.evaluate((el: HTMLButtonElement) => el.click());
        await page.waitForTimeout(2000);
        expect(captured?.session_metadata?.plugin_type).toBe(t);
      });
    }

    test('consent_dialog_shows_permissions_before_save', async ({ page, request }) => {
      // Simulate a plugin_manifest_ready emission by POSTing fixture via backend helper,
      // OR directly exercise the UI path via builder session end-to-end (v1: use a
      // page.evaluate() to dispatch a synthetic SSE event is overkill; instead, rely
      // on the save-modal precondition: consentModal must open BEFORE saveModal).
      await openPluginsPage(page);
      await clickStart(page);
      const chip = page.locator('[data-testid="plugin-type-chip-tool"]');
      await chip.evaluate((el: HTMLButtonElement) => el.click());

      // Wait for consent modal — selector contract:
      //   data-testid="plugin-consent-modal"
      //   data-testid="plugin-consent-type-chip"
      //   data-testid="plugin-consent-permissions"
      //   data-testid="plugin-consent-allow"
      //   data-testid="plugin-consent-cancel"
      await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 60_000 });
      await expect(page.locator('[data-testid="plugin-consent-type-chip"]')).toContainText('tool');
      await expect(page.locator('[data-testid="plugin-consent-permissions"]')).toBeVisible();
      await expect(page.locator('[data-testid="plugin-consent-allow"]')).toBeVisible();
      await expect(page.locator('[data-testid="plugin-consent-cancel"]')).toBeVisible();
    });

    test('consent_allow_persists_plugin_with_type', async ({ page }) => {
      await openPluginsPage(page);
      await clickStart(page);
      await page.locator('[data-testid="plugin-type-chip-tool"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 60_000 });
      await page.locator('[data-testid="plugin-consent-allow"]').evaluate((el: HTMLButtonElement) => el.click());
      // Original saveModal now opens
      await expect(page.locator('[data-testid="plugin-save-modal"]')).toBeVisible({ timeout: 5_000 });
    });

    test('consent_deny_does_not_persist', async ({ page }) => {
      await openPluginsPage(page);
      await clickStart(page);
      await page.locator('[data-testid="plugin-type-chip-tool"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 60_000 });
      await page.locator('[data-testid="plugin-consent-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
      // consentModal closes, saveModal should NOT open
      await expect(page.locator('[data-testid="plugin-consent-modal"]')).not.toBeVisible();
      await expect(page.locator('[data-testid="plugin-save-modal"]')).not.toBeVisible();
    });

    test('mobile_viewport_consent_buttons_stack_vertically', async ({ page }) => {
      await openPluginsPage(page);
      await clickStart(page);
      await page.locator('[data-testid="plugin-type-chip-tool"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 60_000 });
      const allowBox = await page.locator('[data-testid="plugin-consent-allow"]').boundingBox();
      const cancelBox = await page.locator('[data-testid="plugin-consent-cancel"]').boundingBox();
      // Only enforce stacking on mobile-safari (viewport < 500px wide)
      const vp = page.viewportSize();
      if (vp && vp.width < 500 && allowBox && cancelBox) {
        expect(Math.abs(allowBox.y - cancelBox.y)).toBeGreaterThan(5);
      }
    });
  });
  ```

- [ ] **Step 2**: 运行 — 全 FAIL(UI 元素 + plugin_type metadata 未实现)。
  ```bash
  cd .worktrees/plugin-builder-typed/e2e
  npx playwright test plugin-consent-dialog.spec.ts --project=desktop-chromium --reporter=line --retries=0 2>&1 | tail -10
  ```
  Expected: 6+ FAIL.

- [ ] **Step 3**: Commit RED。
  ```bash
  git add e2e/tests/plugin-consent-dialog.spec.ts
  git commit -m "test(e2e): RED phase — plugin consent dialog + chip → plugin_type dispatch"
  ```

---

## Task 4: Backend — `/plugins/validate-manifest` + type dispatch

**Files:**
- Modify: `backend/app/api/v1/plugins.py` — add `ValidateManifestRequest` + 4 `*Manifest` Pydantic + handler
- Verify: no migration needed(纯应用层)

- [ ] **Step 1**: 在 `plugins.py` 顶部 import 区后,定义 4 个 manifest Pydantic。
  ```python
  # --- Type-specific manifest sub-schemas (ADR-087, Session 4a) ---
  class PluginPermissions(BaseModel):
      allowed_tools: list[str] = Field(default_factory=list)
      allowed_models: list[str] = Field(default_factory=list)
      storage_scope: Literal["session", "user", "global"] = "session"
      network_access: bool = False


  class _BaseManifest(BaseModel):
      name: str = Field(min_length=1)
      version: str = "1.0.0"
      description: str = ""
      permissions: PluginPermissions = Field(default_factory=PluginPermissions)
      model_config = {"extra": "forbid"}


  class ToolManifest(_BaseManifest):
      type: Literal["tool"] = "tool"
      parameters: dict[str, Any] = Field(default_factory=dict)
      returns: str = ""


  class AgentStrategyManifest(_BaseManifest):
      type: Literal["agent_strategy"]
      reasoning_pattern: Literal["react", "plan-and-execute", "debate"]
      max_turns: int = Field(gt=0, le=100, default=10)


  class ExtensionManifest(_BaseManifest):
      type: Literal["extension"]
      hook: Literal["pre_turn", "post_turn", "post_tool_use"]
      middleware_class_path: str = Field(min_length=1)


  class TriggerManifest(_BaseManifest):
      type: Literal["trigger"]
      event_source: Literal["cron", "webhook", "file_watch"]
      config: dict[str, Any] = Field(default_factory=dict)


  _MANIFEST_BY_TYPE: dict[str, type[_BaseManifest]] = {
      "tool": ToolManifest,
      "agent_strategy": AgentStrategyManifest,
      "extension": ExtensionManifest,
      "trigger": TriggerManifest,
  }


  class ValidateManifestRequest(BaseModel):
      manifest: dict[str, Any]


  class ValidateManifestResponse(BaseModel):
      valid: bool
      type: PluginType
      name: str
      permissions: dict[str, Any]
  ```

- [ ] **Step 2**: 新路由 `POST /plugins/validate-manifest`(不改老 `/plugins/validate`,老的处理 plugin_dir)。
  ```python
  @router.post(
      "/validate-manifest",
      response_model=ApiResponse[ValidateManifestResponse],
      summary="校验 plugin manifest 字典(按 type dispatch, ADR-087)",
  )
  async def validate_manifest(
      body: ValidateManifestRequest,
      current_user: Annotated[User, Depends(get_current_user)],
  ) -> ApiResponse[ValidateManifestResponse]:
      m = body.manifest or {}
      ptype = m.get("type", "tool")
      sub = _MANIFEST_BY_TYPE.get(ptype)
      if sub is None:
          raise HTTPException(
              status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
              detail=[{"loc": ["type"], "msg": f"unknown plugin type '{ptype}'"}],
          )
      try:
          # Ensure 'type' is set in the manifest before parsing (Literal match)
          m_normalized = {**m, "type": ptype}
          parsed = sub.model_validate(m_normalized)
      except ValidationError as exc:
          raise HTTPException(
              status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
              detail=exc.errors(),
          ) from exc
      return ApiResponse(data=ValidateManifestResponse(
          valid=True,
          type=parsed.type,
          name=parsed.name,
          permissions=parsed.permissions.model_dump(),
      ))
  ```
  Import add at top: `from pydantic import ValidationError`; ensure `PluginType` Literal still re-exported.

- [ ] **Step 3**: Rebuild backend + rerun unit tests。
  ```bash
  cd .worktrees/plugin-builder-typed
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 8
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_plugin_validate_dispatch.py --no-header 2>&1 | tail -15"
  ```
  Expected: **8/8 PASS**。

- [ ] **Step 4**: Commit。
  ```bash
  git add backend/app/api/v1/plugins.py
  git commit -m "feat(plugins): /plugins/validate-manifest with type-dispatched Pydantic schemas (ADR-087)"
  ```

---

## Task 5: Backend — task_service + schema 透传 session_metadata

**Files:**
- Modify: `backend/app/schemas/task.py` — add `session_metadata: dict`
- Modify: `backend/app/services/task_service.py` — 把 `session_metadata` 序列化传给 executor
- Modify: `executor/engine/prompt_sections.py` — 读 `session_metadata.plugin_type` 切换 prompt body

- [ ] **Step 1**: 在 `backend/app/schemas/task.py` `SubmitTaskRequest` 添加字段(读原文件前先 Read)。
  ```python
  # 在 SubmitTaskRequest 字段末尾添加:
  session_metadata: dict = Field(default_factory=dict, description="Session 级元数据,透传到 executor(如 plugin_type)")
  ```

- [ ] **Step 2**: `backend/app/services/task_service.py` 在 `submit` 方法里把 `session_metadata` 放进传给 executor 的 payload;找到创建 `messages` / 调 executor 的地方,加一行写入。具体定位:
  ```bash
  grep -n "session_metadata\|task_payload\|prompt" backend/app/services/task_service.py | head -10
  ```
  如果 task_service 通过 DB insert messages 让 executor 消费,则直接在 `messages` 元数据字段里 merge `session_metadata`。
  
  具体写法(示意):
  ```python
  # When building the message record for the executor to pick up:
  meta = {**(request.session_metadata or {}), "agent_type": request.agent_type}
  new_msg = Message(..., metadata_=meta)
  ```

- [ ] **Step 3**: `executor/engine/prompt_sections.py` 修改 builder prompt 生成逻辑。
  ```python
  # 找到 PluginBuilder system prompt 的 build 函数(grep 确定)
  grep -n "plugin_builder\|你协助用户构建 Prism 插件" executor/engine/prompt_sections.py
  ```
  
  在 plugin_builder prompt 文本处,插入 type-aware 分支:
  ```python
  _PLUGIN_TYPE_GUIDANCE = {
      "tool": (
          "本次构建 **tool** 类型 plugin。YAML 必含字段:\n"
          "  type: tool\n  parameters: {param_name: type, ...}\n  returns: string | object\n"
          "示例 skeleton:\n"
          "  name: my-tool\n  version: 1.0.0\n  type: tool\n  description: ...\n"
          "  parameters:\n    query: string\n  returns: string\n"
      ),
      "agent_strategy": (
          "本次构建 **agent_strategy** 类型 plugin。YAML 必含字段:\n"
          "  type: agent_strategy\n  reasoning_pattern: react | plan-and-execute | debate\n  max_turns: int(1-100)\n"
      ),
      "extension": (
          "本次构建 **extension** 类型 plugin。YAML 必含字段:\n"
          "  type: extension\n  hook: pre_turn | post_turn | post_tool_use\n  middleware_class_path: '<dotted.path>'\n"
      ),
      "trigger": (
          "本次构建 **trigger** 类型 plugin。YAML 必含字段:\n"
          "  type: trigger\n  event_source: cron | webhook | file_watch\n  config: {...}\n"
      ),
  }

  def build_plugin_builder_prompt(session_metadata: dict | None = None) -> str:
      meta = session_metadata or {}
      ptype = meta.get("plugin_type", "tool")
      guidance = _PLUGIN_TYPE_GUIDANCE.get(ptype, _PLUGIN_TYPE_GUIDANCE["tool"])
      return (
          "你协助用户构建 Prism 插件。引导用户完成 plugin.yaml / SKILL.md / Hook 脚本的结构化配置。\n\n"
          f"{guidance}\n\n"
          "所有字段确认后调用输出工具生成 manifest。提醒用户按 type 要求填入 permissions 字段 "
          "(allowed_tools / allowed_models / storage_scope / network_access)。"
      )
  ```
  
  并把现有调用此 prompt 生成的地方改为传入 session_metadata。

- [ ] **Step 4**: Rebuild + 验证。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 8
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/health/live
  ```

- [ ] **Step 5**: Commit。
  ```bash
  git add backend/app/schemas/task.py backend/app/services/task_service.py executor/engine/prompt_sections.py
  git commit -m "feat(executor): PluginBuilder prompt type-aware via session_metadata (ADR-087)"
  ```

---

## Task 6: Frontend — apiClient + PluginsPage consent dialog

**Files:**
- Modify: `frontend/apiClient.js` — `tasks.submit` 透传 session_metadata
- Modify: `frontend/Prism.html` — PluginsPage:chip click 带 plugin_type;新 consent modal

- [ ] **Step 1**: `apiClient.js` tasks.submit 加参数。
  找到 `tasks = { submit({...}) }` 定义,加 session_metadata:
  ```javascript
  submit({ session_id, prompt, agent_type, session_metadata } = {}) {
    return request('POST', '/tasks', { json: { session_id, prompt, agent_type, session_metadata } });
  },
  ```

- [ ] **Step 2**: `Prism.html` PluginsPage `handleBuilderSend` 接受 `extraMeta` 参数。
  定位:`async function handleBuilderSend(text)` 内,改签名为 `handleBuilderSend(text, extraMeta = {})`,把 `extraMeta` 作为 `session_metadata` 传给 `PrismAPI.tasks.submit`。
  chip click 点击处(Session 3 Phase 1 已有 4 个 `plugin-type-chip-${t}`)改为:
  ```jsx
  onClick={() => {
    setPluginType(t);
    setBuilderStep("chat");
    handleBuilderSend(`我想构建一个 type=${t} 的 plugin。`, { plugin_type: t });
  }}
  ```

- [ ] **Step 3**: 添加 consent modal state + handler(在 saveModal 之前触发)。找到 `case "plugin_manifest_ready"` 的 handler(Session 3 Phase 1 已有),把:
  ```jsx
  setSaveModal(true);
  ```
  改为:
  ```jsx
  setConsentModal({
    name: data.name || "my-plugin",
    type: data.type || pluginType || "tool",
    permissions: data.permissions || {},
    yaml: data.manifest_yaml || "",
    description: data.description || "",
  });
  ```
  新增 state:
  ```jsx
  const [consentModal, setConsentModal] = useState(null);
  ```

- [ ] **Step 4**: Consent Modal 组件(紧贴现有 saveModal 前)。
  **Load skills: `frontend-design` + `ui-ux-pro-max:ui-ux-pro-max`** — 本步前需加载,确保 UI 质量。
  
  ```jsx
  {consentModal && (
    <div data-testid="plugin-consent-modal" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 400, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setConsentModal(null)}>
      <div style={{ background: "var(--paper)", borderRadius: 12, padding: 28, maxWidth: 520, width: "90%", display: "flex", flexDirection: "column", gap: 16 }} onClick={e => e.stopPropagation()}>
        <div>
          <div style={{ fontFamily: "var(--serif)", fontSize: 17, color: "var(--ink)", marginBottom: 6 }}>授权 {consentModal.name}</div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span data-testid="plugin-consent-type-chip" style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12, background: "var(--amber-bg, #fef3c7)", color: "var(--amber-ink, #92400e)", fontFamily: "var(--mono)", fontWeight: 500 }}>
              type: {consentModal.type}
            </span>
          </div>
        </div>
        <div data-testid="plugin-consent-permissions" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "14px 16px", background: "var(--bg)", borderRadius: 8, border: "1px solid var(--line)" }}>
          <div style={{ fontSize: 12, color: "var(--ink-3)", fontFamily: "var(--serif)", fontStyle: "italic" }}>此插件请求以下权限:</div>
          <PermissionRow label="允许调用的工具" value={(consentModal.permissions.allowed_tools || []).join(", ") || "(无)"}/>
          <PermissionRow label="允许使用的模型" value={(consentModal.permissions.allowed_models || []).join(", ") || "(无)"}/>
          <PermissionRow label="存储范围" value={consentModal.permissions.storage_scope || "session"}/>
          <PermissionRow label="网络访问" value={consentModal.permissions.network_access ? "✓ 允许" : "✗ 禁止"}/>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button data-testid="plugin-consent-allow" className="btn primary" style={{ width: "100%", justifyContent: "center" }} onClick={() => {
            setSaveName(consentModal.name);
            setSaveDesc(consentModal.description);
            setSaveYaml(consentModal.yaml);
            setConsentModal(null);
            setSaveModal(true);
          }}>
            允许并保存到插件库
          </button>
          <button data-testid="plugin-consent-cancel" className="btn ghost" style={{ width: "100%", justifyContent: "center" }} onClick={() => setConsentModal(null)}>
            取消
          </button>
        </div>
      </div>
    </div>
  )}
  ```
  
  定义辅助组件 `PermissionRow`(PluginsPage 内部或文件顶部):
  ```jsx
  function PermissionRow({ label, value }) {
    return (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12.5 }}>
        <span style={{ color: "var(--ink-3)" }}>{label}</span>
        <span style={{ fontFamily: "var(--mono)", color: "var(--ink)" }}>{value}</span>
      </div>
    );
  }
  ```
  
  原 saveModal div 加 `data-testid="plugin-save-modal"`(定位现有 saveModal 打开的外层 div)。

- [ ] **Step 5**: handleBuilderSend 调用处传递 session_metadata。定位 `await PrismAPI.tasks.submit(...)`,改:
  ```javascript
  await PrismAPI.tasks.submit({ session_id: sid, prompt: text, agent_type: "plugin_builder", session_metadata: extraMeta });
  ```

- [ ] **Step 6**: Recreate nginx 指向 worktree frontend + 手工 smoke。
  ```bash
  docker compose -p prismv3 up -d --force-recreate nginx 2>&1 | tail -3
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/
  ```

- [ ] **Step 7**: Commit。
  ```bash
  git add frontend/apiClient.js frontend/Prism.html
  git commit -m "feat(frontend): PluginsPage consent dialog + chip → plugin_type session_metadata (Session 4a)"
  ```

---

## Task 7: Run full GREEN + Simplify + PJR

- [ ] **Step 1**: Python unit green。
  ```bash
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_plugin_validate_dispatch.py --no-header 2>&1 | tail -10"
  ```
  Expected: 8/8 passed.

- [ ] **Step 2**: Playwright 双端 consent dialog green。
  ```bash
  cd .worktrees/plugin-builder-typed/e2e
  npx playwright test plugin-consent-dialog.spec.ts --reporter=line --retries=0 2>&1 | tail -10
  ```
  Expected: 16/16 passed(desktop + mobile)。若 builder 响应 >60s 超时,增 test.setTimeout;若 plugin_manifest_ready event 没触发,改 e2e 直接 POST `/plugins/save` 前端测试路径(不完全依赖 SSE event 时序)。
  
  **若 SSE 事件触发不可靠,备选路径**:前端添加一个 **dev-only hidden button** `[data-testid="plugin-consent-force-open"]` 让 test 直接触发 consentModal(注入假的 consentModal state),这样测 UI 逻辑不依赖 executor 真实生成 manifest。更稳。
  
  若选备选:在 PluginsPage 内加:
  ```jsx
  <button data-testid="plugin-consent-force-open" style={{ display: "none" }} onClick={() => setConsentModal({
    name: "test-plugin", type: pluginType || "tool",
    permissions: { allowed_tools: ["fetch"], allowed_models: ["claude-*"], storage_scope: "session", network_access: false },
    yaml: "name: test\ntype: tool\n", description: "test",
  })}/>
  ```
  然后 e2e 用 `page.locator('[data-testid="plugin-consent-force-open"]').evaluate(el => el.click())` 触发。

- [ ] **Step 3**: Simplify skill 3 subagent 并行审查。
  ```
  Load: Skill('simplify')
  ```
  Simplify 会自动派出 3 个 subagent(reuse / quality / efficiency)。修所有 findings。commit(if changes)。

- [ ] **Step 4**: PJR 全跑。
  ```
  Load: Skill('project-review:pjr')
  ```
  - Backend: AST 13 新/改文件 + in-container import + `/plugins/validate-manifest` curl smoke
  - Frontend: `node --check` on apiClient.js; Prism.html 零构建由 Playwright 覆盖
  - 检查 workspace clean + develop ahead count

- [ ] **Step 5**: Commit Simplify + PJR(若有改)。

---

## Task 8: git-merge-to-develop + HANDOFF

- [ ] **Step 1**: 加载 `Skill('git-merge-to-develop:git-merge-to-develop')`,按其 rebase + merge 流程(无 remote,local merge --no-ff 按 Session 3 precedent)。
  ```bash
  cd "E:/Agent program/PrismV3"
  git checkout develop
  git merge --no-ff redesign/plugin-builder-typed -m "Merge Session 4a: Plugin Builder type-aware + consent dialog (ADR-087 偏离点清零)"
  ```

- [ ] **Step 2**: 跑 develop HEAD 完整 playwright 回归(双端)。
  ```bash
  docker compose -p prismv3 up -d --force-recreate nginx 2>&1 | tail -3
  cd e2e && npx playwright test --reporter=line --retries=0 2>&1 | tail -6
  ```
  Expected: ≥38p + 16 新 = ≥54 passed,零回归。

- [ ] **Step 3**: 更新 `HANDOFF-LOG.md` Session 4a 完成条目 + 4b/4c/4d 下一 session SOP;更新 `DECISIONS.md` ADR-087 偏离点状态从 "未做" → "✅ Session 4a 完成"。

- [ ] **Step 4**: Commit HANDOFF + DECISIONS。

---

## Self-Review Checklist(planning)

1. **Spec coverage**:spec §3.1 / §3.2 / §3.3 全有对应 task(Task 5 / Task 4 / Task 6)✓;spec §8.1 unit 8 tests → Task 2 实现 ✓;§8.2 e2e 8 tests(16 dual viewport)→ Task 3 ✓
2. **Placeholder scan**:Task 5 Step 2 "grep 确定" 是合理探测步(非 TBD 占位);Task 7 Step 2 有"若失败备选 force-open button"细节,非占位
3. **Type consistency**:`PluginPermissions.storage_scope` Literal 与 spec §3.3 / Task 4 一致 ✓;`plugin_type` chip id 与 Session 3 Phase 1 `plugin-type-chip-${t}` 既定一致 ✓
4. **ADR 对齐**:ADR-087 偏离点 #2 #3 #4 全覆盖

---

## Execution notes

- 单 session 完整执行(spec + 8 Tasks)需 2-3h context。若 context 紧张可 Task 7 后分段(先 merge 再 HANDOFF)
- Simplify + PJR 是 required quality gate,不可跳过(用户 explicit 要求)
- Playwright 桌面 + 移动端每 test 都要跑,fail 一次通过 retries=0 确认稳定
- 一旦 detect scope creep(比如想顺手改 builder agent 完整度打分 ADR-038),halt + blocker.md
