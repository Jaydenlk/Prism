# Prism 棱镜 v2 — Frontend Features (DOC-11)

> **文档编号**: DOC-11  
> **版本**: 3.1
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 全部前端页面和功能，逐页对照 Poco 功能清单  
> **前置依赖**: DOC-10（前端基础架构）, DOC-06-09（全部后端 API）  
> **Phase**: 3（前端）  
> **Task 数**: 4  
> **审计关注点**:  
> - **用量仪表盘的数据来源**依赖 `runs.input_tokens` / `runs.output_tokens` / `runs.cost_usd` 三个字段（DOC-01 v3 §4.2），通过 DOC-09 Task 9.2 的 UsageService 聚合。前端不做本地计算，直接消费后端聚合结果

---

## 目录

1. [Task 11.1: 对话界面](#task-111-对话界面)
2. [Task 11.2: 会话管理与搜索](#task-112-会话管理与搜索)
3. [Task 11.3: 设置页面（Provider / MCP / IM）](#task-113-设置页面)
4. [Task 11.4: 用量仪表盘与 Admin 面板](#task-114-用量仪表盘与-admin-面板)
5. [Task 11.5: Skills 商店 & 插件创建 UI](#task-115-skills-商店--插件创建-ui)

---

## Task 11.1: 对话界面

### Part A — 设计与解释

#### 问题陈述

对话界面是 Prism 的核心交互页面。需要支持：文本消息的 streaming 渲染、工具调用卡片、Coordinator 步骤展示、Harness 治理通知（来自 SSE `harness_event`）、消息输入框、新会话/继续会话。

#### 组件架构

```
ChatPage
├── ChatHeader（标题 + 状态指示 + Harness 健康状态）
├── MessageList
│   ├── UserMessage
│   ├── AssistantMessage（streaming 打字效果）
│   ├── ToolCallCard（折叠/展开，显示名称/参数/结果/耗时）
│   ├── HarnessNotice（⚡ 护栏拦截/循环检测/Compaction 等）
│   ├── PlanStepList（Coordinator 模式的步骤列表）
│   └── RunStatusBar（完成/失败/token 用量）
├── QueueIndicator（排队状态提示）
└── ChatInput（输入框 + 发送按钮 + Agent 类型选择器）
```

#### 状态 UI 规范

- **Loading 态**：骨架屏（Skeleton）替代 spinner，保持布局稳定
- **Empty 态**：居中插图 + 引导文案 + 操作按钮（如"创建第一个会话"）
- **Error 态**：内联错误提示 + 重试按钮，不使用全屏错误页
- **Offline 态**：顶部横幅提示"网络连接已断开"，灰色覆盖交互区域

#### 验收标准

- 文本 streaming 渲染（逐字出现）
- 工具调用卡片展示（折叠/展开）
- Harness 治理通知按 DOC-10 §Task 10.2 的策略展示
- 输入框支持 Shift+Enter 换行、Enter 发送
- 排队状态实时更新
- Run 完成后显示 token 用量
- Playwright E2E 桌面端(1280x800) + 移动端(375x812) 通过

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的核心对话界面。DOC-10 的 SSE 客户端和设计系统已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design
- uiuxpromax

## 要创建的文件

```
frontend/src/
├── app/
│   └── chat/
│       ├── page.tsx                # 新会话
│       └── [sessionId]/page.tsx    # 继续会话
├── components/
│   ├── chat/
│   │   ├── ChatHeader.tsx
│   │   ├── MessageList.tsx
│   │   ├── UserMessage.tsx
│   │   ├── AssistantMessage.tsx    # 含 streaming 渲染
│   │   ├── ToolCallCard.tsx
│   │   ├── HarnessNotice.tsx      # ⚡ Harness 治理通知
│   │   ├── PlanStepList.tsx
│   │   ├── RunStatusBar.tsx
│   │   ├── QueueIndicator.tsx
│   │   └── ChatInput.tsx
│   └── ui/                        # shadcn/ui 组件
└── features/
    └── chat/
        └── use-chat.ts            # 对话业务逻辑 Hook
```

## 关键实现细节

### HarnessNotice 组件

```tsx
/**
 * Harness 治理通知组件
 * 
 * 根据 harness_event 的 subtype 差异化展示：
 * - guardrail_trigger / permission_deny → warning badge（黄色/红色）
 * - loop_detected → 阻断通知
 * - compaction → subtle 提示（灰色）
 * - fork_start / fork_end → info badge（蓝色）
 * 
 * 展示在对话流中对应位置（按时间顺序与消息混排）
 */

interface HarnessNoticeProps {
  type: HarnessEventSubtype;
  detail: Record<string, unknown>;
  timestamp: string;
}
```

### RunStatusBar 组件

```tsx
/**
 * Run 完成状态栏
 * 
 * 显示：
 * - 完成/失败状态
 * - 循环次数（turn_count）
 * - Token 用量（input + output）
 * - 成本（cost_usd，如果有）
 * - Harness 摘要（护栏触发次数等，从 harness_summary 读取）
 */
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test chat.spec.ts
# E2E: 桌面端 1280x800 + 移动端 375x812
# 测试场景: 发消息 → streaming → 工具调用 → 完成
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: chat interface with streaming + tool cards + harness notices"`
```

---

## Task 11.2: 会话管理与搜索

### Part A — 设计与解释

#### 问题陈述

用户需要能够浏览、搜索历史会话，并快速切换到已有会话。当前 Part A 缺少组件接口定义和搜索策略。

#### 组件接口

- `SessionListPanel` — 左侧会话列表（支持搜索 + 分页加载）
- `SessionSearchBar` — 搜索栏（按标题全文搜索，debounce 300ms）
- `SessionCard` — 会话卡片（标题、最后消息预览、时间、未读标记）

#### 搜索策略

- 前端：TanStack Query 的 `useInfiniteQuery` 分页 + 搜索防抖
- 后端：`GET /sessions?q=...&page=...&page_size=20`，标题 ILIKE 搜索

#### 状态 UI 规范

- **Loading 态**：骨架屏（Skeleton）替代 spinner，保持布局稳定
- **Empty 态**：居中插图 + 引导文案 + 操作按钮（如"创建第一个会话"）
- **Error 态**：内联错误提示 + 重试按钮，不使用全屏错误页
- **Offline 态**：顶部横幅提示"网络连接已断开"，灰色覆盖交互区域

#### 验收标准

- 侧边栏会话列表（按 updated_at DESC，置顶优先）
- 会话搜索（按标题和消息预览模糊搜索）
- 会话右键菜单（重命名/置顶/删除）
- 删除确认弹窗
- 新建会话按钮

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 要创建的文件

```
frontend/src/
├── components/
│   └── sidebar/
│       ├── SessionList.tsx
│       ├── SessionItem.tsx
│       ├── SessionSearch.tsx
│       └── NewSessionButton.tsx
└── features/
    └── sessions/
        └── use-sessions.ts       # TanStack React Query hooks
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test sessions.spec.ts
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: session list + search + context menu"`
```

---

## Task 11.3: 设置页面（Provider / MCP / IM）

### Part A — 设计与解释

#### 问题陈述

设置页面需要管理 Provider、MCP Server、IM 绑定三类配置。当前 Part A 缺少表单校验规范。

#### 表单校验规范

- Provider 表单：API Key 必填 + 格式校验（sk- 前缀）、Base URL 格式校验、连通性测试按钮
- MCP Server 表单：Name 唯一性校验、Command 必填、JSON Schema 校验 args
- IM 绑定：配对码 6 位数字校验、绑定状态实时刷新

#### 状态 UI 规范

- **Loading 态**：骨架屏（Skeleton）替代 spinner，保持布局稳定
- **Empty 态**：居中插图 + 引导文案 + 操作按钮（如"创建第一个会话"）
- **Error 态**：内联错误提示 + 重试按钮，不使用全屏错误页
- **Offline 态**：顶部横幅提示"网络连接已断开"，灰色覆盖交互区域

#### 验收标准

- Provider 管理页：列表 + 新增（预设选择 / 自定义）+ 编辑 + 删除 + 连通性测试 + 健康状态展示
- MCP Server 管理页：列表 + 安装/卸载 + 启用/禁用 + 配置覆盖
- IM 绑定页：绑定列表 + 生成配对码 + 解绑
- API Key 只展示掩码，编辑时可更新

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 要创建的文件

```
frontend/src/
├── app/
│   └── settings/
│       ├── page.tsx               # 设置主页
│       ├── providers/page.tsx
│       ├── mcp/page.tsx
│       └── im/page.tsx
├── components/
│   └── settings/
│       ├── ProviderForm.tsx       # 新增/编辑 Provider 表单（含预设下拉）
│       ├── ProviderCard.tsx       # Provider 卡片（健康状态 + 测试按钮）
│       ├── MCPServerCard.tsx
│       └── IMBindingCard.tsx
└── features/
    └── settings/
        ├── use-providers.ts
        ├── use-mcp.ts
        └── use-im-bindings.ts
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test settings.spec.ts
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: settings pages (Provider + MCP + IM)"`
```

---

## Task 11.4: 用量仪表盘与 Admin 面板

### Part A — 设计与解释

#### 问题陈述

用户和 Admin 需要看到 Token 消耗和成本趋势。数据来源是 DOC-09 Task 9.2 的 UsageService，后端已完成 `runs.input_tokens` / `runs.output_tokens` / `runs.cost_usd` 的聚合。前端只负责展示，不做本地计算。

#### 用量仪表盘内容

- 汇总卡片：总 Runs、总 Tokens、总成本
- 按 Provider 的用量饼图
- 按日/周/月的趋势折线图
- 最近 10 次 Run 的详情列表（含 harness_summary 摘要：护栏触发次数、Compaction 次数等）

#### Admin 面板

- 全局用量统计（所有用户汇总）
- 用户列表管理
- 邀请码管理
- 审计日志查看（支持 `harness.*` action 筛选）

#### 状态 UI 规范

- **Loading 态**：骨架屏（Skeleton）替代 spinner，保持布局稳定
- **Empty 态**：居中插图 + 引导文案 + 操作按钮（如"创建第一个会话"）
- **Error 态**：内联错误提示 + 重试按钮，不使用全屏错误页
- **Offline 态**：顶部横幅提示"网络连接已断开"，灰色覆盖交互区域

#### 验收标准

- 用量数据从 `/providers/usage` API 获取
- 图表渲染正常（推荐 recharts）
- Admin 面板 only visible for admin role
- harness_summary 中的关键指标在 Run 详情中展示
- Playwright E2E 通过

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的用量仪表盘和 Admin 面板。后端 UsageService 和 Admin API 已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design
- uiuxpromax

## 要创建的文件

```
frontend/src/
├── app/
│   ├── usage/page.tsx             # 用量仪表盘
│   └── admin/
│       ├── page.tsx               # Admin 首页
│       ├── users/page.tsx
│       ├── invites/page.tsx
│       └── audit/page.tsx         # 审计日志（含 harness.* 筛选）
├── components/
│   ├── usage/
│   │   ├── SummaryCards.tsx        # 汇总卡片
│   │   ├── ProviderPieChart.tsx    # 按 Provider 饼图
│   │   ├── UsageTrendChart.tsx     # 趋势折线图（recharts）
│   │   └── RecentRunsList.tsx      # 最近 Run 列表（含 harness_summary 摘要）
│   └── admin/
│       ├── UserTable.tsx
│       ├── InviteCodeTable.tsx
│       └── AuditLogViewer.tsx      # 支持 action 前缀筛选
└── features/
    ├── usage/
    │   └── use-usage.ts            # 调用 /providers/usage API
    └── admin/
        └── use-admin.ts
```

## 关键实现细节

### RecentRunsList 组件

```tsx
/**
 * 最近 Run 列表
 * 
 * 每个 Run 显示：
 * - 状态（completed / failed）
 * - 时间
 * - Token 用量（input_tokens + output_tokens）
 * - 成本（cost_usd）
 * - Harness 摘要（从 run.harness_summary 提取关键指标）：
 *   - 护栏触发次数（guardrail_triggers）
 *   - 循环次数（turn_count）
 *   - Compaction 次数（compaction_events.length）
 *   - 路由模式（route_mode + route_agent_type）
 * 
 * ⚠️ 数据来源：GET /runs/{id}，harness_summary 字段的 schema
 *    定义在 DOC-07 前置定义中。消费时对缺失字段用默认值兜底。
 */
```

### AuditLogViewer 组件

```tsx
/**
 * 审计日志查看器
 * 
 * 支持 action 前缀筛选下拉：
 * - 全部
 * - user.* （用户操作）
 * - harness.* （Harness 治理事件）
 *   - harness.guardrail_trigger
 *   - harness.permission_deny
 *   - harness.circuit_break
 *   - harness.loop_detected
 *   - harness.compaction_trigger
 * 
 * 数据来源：GET /admin/audit-logs?action=harness.&page=1&per_page=50
 */
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test usage.spec.ts
npx playwright test admin.spec.ts
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: usage dashboard + admin panel with harness audit filtering"`
```

---

---

## Task 11.5: Skills 商店 & 插件创建 UI

### Part A — 设计与解释

#### 问题陈述

Prism v3.1 新增 Skills 市场（DOC-05 Task 5.5~5.7）和 PluginBuilder Agent（DOC-04 Task 4.5），需要对应的前端页面：Skills 商店浏览/安装页、插件创建多轮对话向导页、以及 Harness 配置管理页。

#### Skills 商店页面 (`/skills`)

**页面结构（ASCII wireframe）**：

```
┌─────────────────────────────────────────────────────┐
│ Skills 市场                                          │
├─────────────────────────────────────────────────────┤
│ [搜索框: 搜索 Skills...]  [源筛选: 全部|Manus|npm|GitHub|已安装] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Skill A  │  │ Skill B  │  │ Skill C  │          │
│  │ 描述...  │  │ 描述...  │  │ 描述...  │          │
│  │ @manus   │  │ @npm     │  │ @github  │          │
│  │ v1.2.0   │  │ v2.0.1   │  │ v0.3.0   │          │
│  │ [安装]   │  │ [已安装] │  │ [安装]   │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                                                     │
│  ... 更多 Skills 卡片（分页加载）                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**组件清单**：

```
src/features/skills/
├── SkillsStorePage.tsx          # 页面容器
├── SkillSearchBar.tsx           # 搜索栏 + 源筛选器
├── SkillCard.tsx                # Skill 卡片（名称、描述、源标识、版本、操作按钮）
├── SkillGrid.tsx                # 卡片网格 + 分页
├── SkillDetailDrawer.tsx        # 点击卡片后的详情抽屉（README、版本历史、依赖）
├── InstallConfirmDialog.tsx     # 安装确认弹窗（权限声明、来源说明）
├── InstalledSkillsList.tsx      # 已安装 Tab（启用/禁用/卸载/更新）
├── use-skills.ts                # Skills 数据 Hook（search/install/uninstall/update）
└── skills-api.ts                # Skills API 客户端
```

#### 插件创建向导页 (`/plugins/create`)

**页面结构（左右布局）**：

```
┌─────────────────────────────────────────────────────┐
│ 创建插件                                             │
├──────────────────┬──────────────────────────────────┤
│                  │                                  │
│  对话区           │  实时预览                         │
│  ┌────────────┐  │  ┌────────────────────────────┐  │
│  │ PluginBuild│  │  │ 阶段: 需求收集 (3/5)       │  │
│  │ er Agent   │  │  ├────────────────────────────┤  │
│  │ 对话消息... │  │  │                            │  │
│  │            │  │  │ 插件结构预览（实时更新）     │  │
│  │            │  │  │ ├── plugin.yaml             │  │
│  │            │  │  │ ├── skills/                 │  │
│  │            │  │  │ │   ├── skill-a/            │  │
│  │            │  │  │ │   └── skill-b/            │  │
│  │            │  │  │ └── hooks/                  │  │
│  │            │  │  │                            │  │
│  └────────────┘  │  └────────────────────────────┘  │
│  [输入框...]     │                                  │
│                  │  [确认设计] (阶段2时才可点击)      │
│                  │                                  │
└──────────────────┴──────────────────────────────────┘
```

**关键交互**：

- 左侧是标准对话界面，底层走 PluginBuilder Agent
- 右侧实时预览随对话进展动态更新
- 阶段指示器显示当前进度（需求收集 → 设计确认 → 生成 → 验证）
- "确认设计"按钮只有在 Agent 展示完设计方案后才可点击（前端根据 Agent 消息中的阶段标记判断）

**组件清单**：

```
src/features/plugins/
├── PluginCreatePage.tsx         # 页面容器（左右布局）
├── PluginChatPanel.tsx          # 左侧对话面板（复用 ChatMessage 组件）
├── PluginPreviewPanel.tsx       # 右侧实时预览
├── PluginPhaseIndicator.tsx     # 阶段进度指示器
├── PluginStructureTree.tsx      # 插件目录结构树预览
├── ConfirmDesignButton.tsx      # 确认设计按钮（条件可用）
├── use-plugin-builder.ts        # PluginBuilder 业务逻辑 Hook
└── plugin-builder-api.ts        # 对话 API（复用 /tasks 端点，指定 agent_type）
```

#### Harness 配置页 (`/settings/harness`)

**组件清单**：

```
src/features/settings/
├── HarnessConfigPage.tsx        # Harness 配置页容器
├── GuardrailRulesList.tsx       # Guardrail 规则列表（启用/禁用/编辑/添加）
├── MiddlewareTogglePanel.tsx    # Middleware 开关面板（P7 可撕裂的 UI 体现）
├── PermissionPolicyEditor.tsx   # 权限策略编辑器
├── ConfigSourceTrace.tsx        # 配置来源追踪（每条配置标注来自哪个源）
└── use-harness-config.ts        # Harness 配置 Hook
```

#### 状态 UI 规范

- **Loading 态**：骨架屏（Skeleton）替代 spinner，保持布局稳定
- **Empty 态**：居中插图 + 引导文案 + 操作按钮（如"创建第一个会话"）
- **Error 态**：内联错误提示 + 重试按钮，不使用全屏错误页
- **Offline 态**：顶部横幅提示"网络连接已断开"，灰色覆盖交互区域

#### 验收标准

- Skills 商店页面：搜索、安装、卸载流程完整走通（Playwright E2E）
- 插件创建向导：完整多轮对话 → 确认 → 生成流程（Playwright E2E）
- Harness 配置页：修改 Guardrail 规则后立即生效
- 所有页面桌面端 + 移动端双视口测试通过
- 正常流程 + 边界场景（搜索无结果、安装失败、网络错误）全覆盖

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Skills 商店、插件创建向导和 Harness 配置页。后端 Skills Market API（DOC-05 Task 5.5~5.6）和 PluginBuilder Agent（DOC-04 Task 4.5）已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design
- uiuxpromax

## 要创建的文件

```
frontend/src/
├── app/
│   ├── skills/page.tsx                  # Skills 商店页
│   ├── plugins/
│   │   └── create/page.tsx              # 插件创建向导页
│   └── settings/
│       └── harness/page.tsx             # Harness 配置页
├── features/
│   ├── skills/
│   │   ├── SkillsStorePage.tsx
│   │   ├── SkillSearchBar.tsx
│   │   ├── SkillCard.tsx
│   │   ├── SkillGrid.tsx
│   │   ├── SkillDetailDrawer.tsx
│   │   ├── InstallConfirmDialog.tsx
│   │   ├── InstalledSkillsList.tsx
│   │   ├── use-skills.ts
│   │   └── skills-api.ts
│   ├── plugins/
│   │   ├── PluginCreatePage.tsx
│   │   ├── PluginChatPanel.tsx
│   │   ├── PluginPreviewPanel.tsx
│   │   ├── PluginPhaseIndicator.tsx
│   │   ├── PluginStructureTree.tsx
│   │   ├── ConfirmDesignButton.tsx
│   │   ├── use-plugin-builder.ts
│   │   └── plugin-builder-api.ts
│   └── settings/
│       ├── HarnessConfigPage.tsx
│       ├── GuardrailRulesList.tsx
│       ├── MiddlewareTogglePanel.tsx
│       ├── PermissionPolicyEditor.tsx
│       ├── ConfigSourceTrace.tsx
│       └── use-harness-config.ts
```

## 关键实现细节

### Skills API 调用

```ts
// skills-api.ts
// GET /skills/search?q=...&source=...
// GET /skills/installed
// POST /skills/install  { package_id, source, version? }
// DELETE /skills/{name}
// POST /skills/{name}/update
// GET /skills/{name}
```

### PluginBuilder 对话

```ts
// plugin-builder-api.ts
// 复用 POST /tasks 端点，body 中指定 agent_type: "plugin_builder"
// SSE 流处理同 Chat 页，额外解析 metadata.plugin_build_phase 和 metadata.plugin_structure_preview
```

### Harness 配置 API

```ts
// use-harness-config.ts
// GET /harness/config      — 获取当前有效配置（含 source_trace）
// PATCH /harness/config    — 更新配置（admin only）
// POST /harness/config/reload  — 强制重载
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test skills.spec.ts
npx playwright test plugin-create.spec.ts
npx playwright test harness-config.spec.ts
# E2E: 桌面端 1280x800 + 移动端 375x812
# skills.spec.ts: 搜索 → 安装确认 → 已安装列表
# plugin-create.spec.ts: 多轮对话 → 确认设计 → 生成阶段
# harness-config.spec.ts: 修改规则 → 保存 → 验证生效
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: skills store + plugin create wizard + harness config UI"`
```

---

> **文档维护说明**：本文档的 5 个 Task 完成后，Prism v2 将拥有完整的前端功能：对话界面（streaming + 工具卡片 + Harness 通知）+ 会话管理 + 设置页面（Provider/MCP/IM）+ 用量仪表盘（数据来源：runs 表聚合）+ Admin 面板（含 Harness 审计日志筛选）+ Skills 商店（多源浏览/安装）+ 插件创建向导（PluginBuilder Agent 多轮对话）+ Harness 配置页（垂类规则管理）。
> **最后更新**: 2026-04-05 | **下一步**: DOC-12 Observability & Entropy
