# Session 4a Design: Plugin Builder type-aware + Install Consent Dialog

**Date**: 2026-04-20
**Branch planned**: `redesign/plugin-builder-typed` off `develop`
**DOC assignment**: DOC-SK2 (续 Phase 1 DOC-SK 的 ADR-087 偏离点清零)
**Parent ADR**: ADR-087 (Typed Plugin Manifest + Permissions) — 本 spec 补完其 Phase 1 未做的 3 项偏离点

---

## 1. Source of truth

- ADR-087 偏离点 #2: "`/validate` endpoint dispatch on type" — 未做
- ADR-087 偏离点 #3: "type-specific sub-schema 未实现"
- ADR-087 偏离点 #4: "install consent dialog 未实现"
- Phase 1 spec §5.2: 四类 type 定义 + 各自字段要求

User directive (2026-04-20): "真正生产可用,不是 mock;桌面 + 移动端 Playwright 每按钮人工模拟。"
Open principles:**单一职责 / 最简代码 / 类型严格 / KISS / 文档置信度**。

---

## 2. Scope

### In scope
1. **Executor 侧 `PluginBuilder` agent prompt 按 `type` 分支** — `executor/engine/prompt_sections.py` 加载 plugin_builder system prompt 时注入 type-specific guidance + YAML skeleton
2. **`POST /api/v1/plugins/validate` 按 `manifest.type` dispatch** — 四种 type 各自的 Pydantic sub-schema,错误位置精确到 field
3. **前端 `PluginsPage` Install Consent Dialog** — 在 `saveModal` 之前插入 consent step,显示 permissions 声明 + 允许/取消按钮;取消则不 POST `/plugins/save`
4. **`apiClient.plugins.save` 透传 type + permissions**(Phase 1 已做,本 session 验证 wiring)
5. **Playwright e2e** — 桌面 + 移动端各验证:4 chips 选择 → builder 生成对应 type YAML → consent dialog 显示 permissions → allow 写 DB(plugin_type 正确存)/ deny 不写 DB

### Out of scope (hard)
- type 之间的迁移(改 type 相当于重建)
- 运行时 permission enforcement(declaration + consent 本 session;runtime enforcement 独立 session)
- 插件 hot-reload(当前已 enabled 字段,本 session 不动)
- IM / Skills Market / 分布式任务拆解

---

## 3. Architecture

### 3.1 Executor — PluginBuilder agent type-aware prompt

当前(`executor/engine/prompt_sections.py:261`)PluginBuilder system prompt 是 type-agnostic,只通用介绍构建 plugin.yaml / SKILL.md / Hook。

改动:
- `build_plugin_builder_prompt(session_metadata)` 读取 `session_metadata.get("plugin_type")`(前端在 start session 时 POST 到 tasks.submit 带上)
- 根据 type 切换 prompt body:
  - `tool`: OpenAPI-like tool 定义指引 + `name/description/parameters/returns` YAML 示例
  - `agent_strategy`: `reasoning_pattern: react|plan-and-execute|debate` + `max_turns: int` 指引
  - `extension`: `hook: pre_turn|post_turn|post_tool_use` + `middleware_class_path: str`
  - `trigger`: `event_source: cron|webhook|file_watch` + `config: dict`
- 若 `plugin_type` 缺省 → 默认 `tool`(ADR-087 Pydantic 默认一致)

type 切换点在 system prompt build 一次完成,不动 query_engine 循环。符合"进程边界 = 信任边界"。

### 3.2 Backend — `/plugins/validate` type dispatch

当前 `/plugins/validate` 仅校验 `manifest_yaml` 存在且可读,不按 type 区分。

改动 `backend/app/api/v1/plugins.py`:
- 新增 `PluginTypeSubSchema` 基类;四个具体 class(`ToolManifest / AgentStrategyManifest / ExtensionManifest / TriggerManifest`)
- `validate_plugin` handler:解析 `manifest_yaml` → 读 `type` field → dispatch 到对应 sub-schema `.model_validate(body)`;报错时 Pydantic `ValidationError` → HTTPException 422 + `detail` 含 `loc` + `msg`
- 合法 type 枚举集中在 ADR-087 定义的 `Literal["tool", "agent_strategy", "extension", "trigger"]`
- 未知 type → 422 "unknown plugin type '{value}'"

### 3.3 Frontend — Install Consent Dialog

当前(`frontend/Prism.html`):
- Builder 生成 manifest 后触发 `saveModal = true`
- Modal 显示 name / description / YAML,点击"保存到插件库" → POST `/plugins/save`

改动:**在 `saveModal` 之前插入 `consentModal`**
- 新 state `consentModal: {open, type, permissions, yaml, name, description}`
- 触发点:builder agent emit `plugin_manifest_ready` 事件(已有)时,**先** `setConsentModal(...)` 而不是直接 `setSaveModal(true)`
- UI(按 frontend-design + ui-ux-pro-max 原则):
  - Header: "授权 {name}"(serif)
  - Type chip:显示当前 type(amber 胶囊,同 PluginsPage 4 chips 同 token)
  - Permissions section:
    - `allowed_tools`: monospace 列表
    - `allowed_models`: monospace 列表
    - `storage_scope`: 单行 `session | user | global`
    - `network_access`: `✓ 允许` / `✗ 禁止` 图标
  - Footer 两按钮:
    - **允许并保存** (primary,amber) → 转入原 saveModal 流程 → POST `/plugins/save`
    - **取消** (ghost) → 关闭 consent modal + 不保存

类名:`.consent-dialog` + `.permission-row` + `.permission-chip`(复用 `--paper/--ink/--amber/--panel/--line` tokens)

---

## 4. 决策(auto-decide per user directive)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | 前端 consent 显示 vs 运行时 enforcement | 仅显示 + 用户 consent | 运行时 enforcement 跨 DOC(涉及 executor tool dispatcher + MCP gate + model selector),独立 session |
| D2 | type 缺省 | 默认 `tool`(与 ADR-087 Pydantic/DB server_default 对齐) | 一致性;旧行为兼容 |
| D3 | consent 取消后是否销毁 manifest | **是** — 不落 DB 也不缓存 | 符合 consent 语义;取消即重新 builder |
| D4 | type 切换是否允许改已存 plugin | **不允许** — 需删后重建 | "不做向后兼容"原则;避免 permissions 漂移 |
| D5 | 未知 type 的 `save` 行为 | 422 拒绝(Phase 1 已做,本 session 添加 validate 一致) | fail-closed |
| D6 | consent modal 移动端布局 | 上下堆叠 + 按钮全宽 | mobile-safari viewport 330px 宽,横向 2 按钮会挤 |

---

## 5. 数据流

```
用户点 chip (type=extension)
  ↓
PluginsPage.handleBuilderSend("我想构建...", {plugin_type: "extension"})
  ↓
tasks.submit {session_id, prompt, agent_type: plugin_builder, session_metadata: {plugin_type}}
  ↓
executor PluginBuilder agent 加载 type-aware prompt (extension skeleton)
  ↓
SSE stream 生成 YAML
  ↓
emit plugin_manifest_ready {name, type, permissions, manifest_yaml}
  ↓
前端 setConsentModal(...)
  ↓
用户点"允许并保存" → setSaveModal(true) → 原流程 → POST /plugins/save {type, permissions}
     or
用户点"取消" → setConsentModal(null) → 销毁
```

---

## 6. Schema changes

**无 migration**。Phase 1 已在 `plugins_library.plugin_type + permissions_json` 落地。本 session 只消费已存 schema。

---

## 7. Environment / dependencies

**无**新环境变量或依赖。所有改动在现有进程边界内。

---

## 8. 验证方案

### 8.1 Python unit
- `backend/tests/test_plugin_validate_dispatch.py`(新):4 type × 合法/非法各一 = 8 tests
  - `test_tool_manifest_valid_passes`
  - `test_tool_manifest_missing_name_422`
  - `test_agent_strategy_missing_reasoning_pattern_422`
  - `test_extension_unknown_hook_422`
  - `test_trigger_missing_event_source_422`
  - `test_unknown_type_422`
  - `test_type_defaults_to_tool_when_absent`
  - `test_permissions_parsed_into_pydantic`

### 8.2 Playwright(桌面 + 移动端,覆盖每个 chip + consent allow/deny)
`e2e/tests/plugin-consent-dialog.spec.ts`(新):
- `chip_tool_triggers_type_tool_manifest` — 点 tool chip,验 builder response 包含 `type: tool` YAML
- `chip_agent_strategy_triggers_type_agent_strategy_manifest`
- `chip_extension_triggers_type_extension_manifest`
- `chip_trigger_triggers_type_trigger_manifest`
- `consent_dialog_shows_permissions_before_save`
- `consent_allow_persists_plugin_with_type`
- `consent_deny_does_not_persist`
- `mobile_viewport_buttons_stack_vertically`

双 viewport × 8 tests = **16 新 e2e**。

### 8.3 手动 sim(Playwright headed 验证)
每个 chip × allow / deny,共 8 路径;mobile viewport 再跑 8;合计 16 人工模拟路径 —— 已由 e2e 自动化覆盖,人工只需运行命令。

---

## 9. 出 scope(hard)

- IM / Skills Market / 分布式任务拆解(Phase 4b/4c/4d+)
- 真实 permission enforcement
- plugin hot-reload
- cc_compat.py 的 plugin.yaml 扩展(executor 级 schema 已有,不动)

---

## 10. Acceptance

- 8 Python unit + 16 e2e(dual viewport)全绿
- `Simplify` 3 并行 subagent 跑完 + 修 findings
- `PJR`:AST / import / frontend node --check / 合并前 lint gate
- `git-merge-to-develop` 本地 no-ff merge 到 develop
- HANDOFF 写 Phase 4a 完成 + 4b/4c/4d 下一 session SOP

---

*End of Session 4a spec — word count ≈ 1400.*
