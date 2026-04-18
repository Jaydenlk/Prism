# Prism 棱镜 v2 — Frontend Features (DOC-11)

> **文档编号**: DOC-11
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — 全部前端页面和功能,参考 Poco 68 文件架构但不 fork 代码(体积 <10MB)
> **前置依赖**: DOC-10 v4(前端基础架构,含 useSSE / apiClient / 视觉系统 / 基础组件库), DOC-06 v4 ~ DOC-09 v4(全部后端 API)
> **Phase**: 3(前端)
> **Task 数**: 6(v4 新增 Task 11.6 Admin Obs 面板)
> **v4 变更摘要**: 基于 5 轮 review 修订,22 处精确修补(详见文末 §附录 A)。核心修订:**Chat 界面扩充**(permission_ask 弹窗 / coordinator plan 可视化 / run_crashed 恢复提示 / ChatHeader 双态)、Session 管理扩充(export/import/share/fork/archive/tag/多选批量)、IM 绑定 UX 完整配对码流程、**用量仪表盘补 Cache 命中率卡 + 节省金额 + Provider 饼图 + 趋势折线**、**Skills Store 拆为 3 个子页**(Skills Store / Plugin Builder / Harness Config)、**新增 Task 11.6 Admin Obs 面板**(专职消费 DOC-12 API)、Playwright E2E 桌面+移动双视口、结构化错误上报。ADR 编号从 ADR-100 接续至 ADR-108。
> **审计关注点**:
> - **用量仪表盘的数据来源**依赖 `runs.input_tokens` / `runs.output_tokens` / `runs.cache_hit_tokens` / `runs.cache_creation_tokens` / `runs.cost_usd`(DOC-01 v4 §4.2),通过 DOC-09 v4 Task 9.2 的 UsageService 聚合。前端不做本地计算,直接消费后端聚合结果
> - **Poco 功能保留 vs 体积**:参考 Poco 68 文件架构完整保留功能(会话管理/分享/fork/tag 等),但不 fork Poco 代码。从零实现,体积 <10MB

---

## 目录

1. [Task 11.1: 对话界面(v4:扩充 permission/plan/crash)](#task-111-对话界面)
2. [Task 11.2: 会话管理与搜索(v4:扩充 export/share/fork/tag)](#task-112-会话管理与搜索)
3. [Task 11.3: 设置页面(v4:IM 绑定 UX 扩充)](#task-113-设置页面)
4. [Task 11.4: 用量仪表盘(v4:Cache 卡 + 节省金额)](#task-114-用量仪表盘与-admin-面板)
5. [Task 11.5: Skills Store / Plugin Builder / Harness Config(v4:拆 3 页)](#task-115-skills-商店--插件创建-ui)
6. [Task 11.6: Admin Observability 面板(v4 新增)](#task-116-admin-observability-面板)

---

## Task 11.1: 对话界面

### Part A — 设计与解释

#### 问题陈述

对话界面是 Prism 的核心交互页面。需要支持：文本消息的 streaming 渲染、工具调用卡片、Coordinator 步骤展示、Harness 治理通知（来自 SSE `harness_event`）、消息输入框、新会话/继续会话。

#### 组件架构(v4 扩充)

```
ChatPage
├── ChatHeader(v4:双态布局,对齐 UI design spec §6)
│   ├── 桌面:标题 + provider 徽章 + cache 命中率 + Harness 健康指示 + 用户菜单
│   └── 移动:Hamburger + 标题 + 状态圆点
├── MessageList
│   ├── UserMessage
│   ├── AssistantMessage(streaming 打字效果)
│   ├── ToolCallCard(复用 DOC-10 v4 <ToolCard>,折叠/展开)
│   ├── HarnessNotice(复用 DOC-10 v4 <HarnessNotification>)
│   ├── PlanStepList / CoordinatorPlanPanel(v4:复用 DOC-10 组件)
│   └── RunStatusBar(完成/失败/token 用量 + cache 节省)
├── PermissionAskModal(v4:复用 DOC-10 组件,SSE permission_ask 触发)
├── RunCrashedBanner(v4 新增:显示"异常中断 + 恢复"按钮,SSE run_crashed 触发)
├── MultiTabErrorBanner(v4:复用 DOC-10 组件,SSE 429 触发)
├── QueueIndicator(排队状态提示)
└── ChatInput(输入框 + 发送按钮 + Agent 类型选择器)
```

#### 状态 UI 规范

- **Loading 态**:骨架屏(Skeleton)替代 spinner,保持布局稳定
- **Empty 态**:居中插图 + 引导文案 + 操作按钮(如"创建第一个会话")
- **Error 态**:内联错误提示 + 重试按钮,不使用全屏错误页
- **Offline 态**:顶部横幅提示"网络连接已断开",灰色覆盖交互区域

#### 设计决策(ADR)

- **ADR-100(ChatHeader 双态布局)**:桌面 / 移动两套布局严格对齐 UI design spec §6 规范,不是简单响应式堆叠。来源:Batch 4 §B4-I。

- **ADR-101(Run 崩溃恢复 UX)**:收到 SSE `run_crashed` 事件时展示 RunCrashedBanner,含"恢复执行"按钮调 `POST /runs/{id}/resume`(依赖 DOC-07 v4 Task 7.4 coordinator_recovery)。仅 coordinator 类型 run 可恢复,其他类型显示"建议重新发起"。

#### 验收标准(v4 扩展)

- 文本 streaming 渲染(逐字出现)
- 工具调用卡片展示(折叠/展开)
- **v4:permission_ask 弹 Modal,用户点击后 POST 到 `/permission-answer`**
- **v4:coordinator_plan_update 事件驱动 CoordinatorPlanPanel 进度更新**
- **v4:run_crashed 事件显示 RunCrashedBanner + 恢复按钮**
- **v4:ChatHeader 桌面/移动双态对齐 UI design spec §6**
- Harness 治理通知按 DOC-10 v4 §Task 10.2 的策略展示
- 输入框支持 Shift+Enter 换行、Enter 发送
- 排队状态实时更新
- Run 完成后显示 token 用量 + cache 节省
- **Playwright E2E 桌面端(1280x800) + 移动端(375x812) 双视口截图基线通过**

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

#### 设计决策(ADR)

- **ADR-102(会话管理扩展)**:v4 保留 Poco 的会话管理功能范围:export(JSON/MD 导出)/ import(导入已导出的会话)/ share(生成只读分享链接)/ fork(基于当前会话新建分支)/ archive(归档,从列表隐藏但不删)/ tag(多标签分组)/ 多选批量(批量归档/删除/导出)。来源:Batch 4 §C-1。

#### 验收标准(v4 扩展)

- 侧边栏会话列表(按 updated_at DESC,置顶优先)
- 会话搜索(按标题和消息预览模糊搜索)
- 会话右键菜单(重命名/置顶/删除)
- 删除确认弹窗
- 新建会话按钮
- **v4:支持 export(JSON/Markdown) / import / share(只读链接) / fork / archive / tag(多标签) / 多选批量操作**

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

#### 设计决策(ADR)

- **ADR-103(IM 绑定 UX 完整流程)**:IM 绑定页完整流程可视化:
  1. 用户点"生成配对码" → 调 `POST /im/bindings/pair` 获得 6 位码
  2. 界面展示配对码 + 倒计时(5 分钟)+ 二维码(小屏扫码)
  3. 提示用户"在飞书/企微/Telegram 对 Prism Bot 发送 `/pair 123456`"
  4. 前端通过 SSE `im.binding.paired` 事件或轮询 `GET /im/bindings` 实时检测
  5. 绑定成功 → 显示"已绑定 + 平台 + 用户名 + 解绑按钮"
  6. 超时过期 → 显示"配对码已过期,重新生成"

  来源:Batch 4 §C-1。

#### 验收标准(v4 扩展)

- Provider 管理页:列表 + 新增(预设选择 / 自定义)+ 编辑 + 删除 + 连通性测试(显示 detected_capabilities 徽章) + 健康状态展示
- MCP Server 管理页:列表 + 安装/卸载 + 启用/禁用 + 配置覆盖
- **v4:IM 绑定页完整流程**:生成配对码(含二维码) → 倒计时 → 实时检测绑定 → 成功展示 → 解绑
- API Key 只展示掩码,编辑时可更新

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

#### 用量仪表盘内容(v4 扩充)

- **汇总卡片**(v4 加 cache):总 Runs、总 Tokens、**Cache 命中率 + cache 节省金额**、总成本
- **按 Provider 的用量饼图**(v4:分层显示 cache_hit / cache_miss / cache_creation tokens)
- **按日/周/月的趋势折线图**(v4:overlay cost_usd + cache_hit_ratio 双轴)
- 最近 10 次 Run 的详情列表(含 harness_summary 摘要:护栏触发次数、Compaction 次数等)

#### 设计决策(ADR)

- **ADR-104(Cache 指标突出展示)**:Cache 命中率和节省金额是 v4 Provider 能力的核心卖点(Anthropic prompt caching 最高节省 90%),仪表盘必须突出展示,不能只是文字。来源:Batch 4 §C-1, Master M7。

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

## Task 11.5: Skills 商店 / Plugin Builder / Harness Config(v4:拆为 3 个子页 + 完整度进度条)

### Part A — 设计与解释

#### 问题陈述

Prism v3.1 新增 Skills 市场(DOC-05 v4 Task 5.5~5.7)和 PluginBuilder Agent(DOC-04 v4 Task 4.5 **v4:完整度打分**),需要对应的前端页面。v4 拆为 3 个独立路由:

1. **`/skills`** — Skills Store(搜索/安装/卸载)
2. **`/plugins/create`** — Plugin Builder 向导(对话 + 实时结构预览 + **完整度进度条**)
3. **`/settings/harness`** — Harness Config **只读展示**(v4:DOC-03 v4 删除了 PATCH API,只保留 GET)

#### 设计决策(ADR)

- **ADR-105(Skills Store 两源)**:源筛选器只显示 `Local / GitHub` 两源(DOC-05 v4 ADR-047),Manus / npm Phase 2 再加。来源:Master M8。

- **ADR-106(Plugin Builder 完整度进度条)**:右侧不仅显示结构预览,还显示 7 个维度的完整度评分进度条(plugin_name / purpose / tools_or_skills / input_output / error_handling / permission_boundary / examples),overall ≥ 0.8 时"生成"按钮才变亮。订阅 SSE 从后端推送的 `plugin_builder.scored` 事件驱动更新。来源:Batch 4 §C-1, DOC-04 v4 ADR-038。

- **ADR-107(Harness Config 只读)**:v4 删除 PATCH API,前端页面只做**展示**:
  - 两列对照表:`代码默认` vs `harness_config.yaml`
  - 每字段显示 source_trace(徽章标注 "default" / "yaml")
  - 底部注释:"修改配置需要编辑 `harness_config.yaml` 并重启服务"
  - 无任何可编辑 input 控件

  来源:Master M8, DOC-03 v4 ADR-031。

#### Skills 商店页面 (`/skills`)

**页面结构（ASCII wireframe）**：

```
┌─────────────────────────────────────────────────────┐
│ Skills 市场                                          │
├─────────────────────────────────────────────────────┤
│ [搜索框: 搜索 Skills...]  [源筛选(v4): 全部|Local|GitHub|已安装] │
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
// use-harness-config.ts(v4:只读)
// GET /harness/config      — 获取当前有效配置(含 source_trace),readonly
// (v4 ADR-107:PATCH 和 reload 端点已在 DOC-03 v4 Task 3.6 删除)
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

---

## Task 11.6: Admin Observability 面板(v4 新增)

### Part A — 设计与解释

#### 问题陈述

v4 新增 DOC-12 Observability API(Harness Analytics / Entropy Alerts / Prometheus metrics / OTel traces)。这些 API 需要对应的前端消费页面。从 DOC-11 的 Admin 面板独立出来作为 Task 11.6,专职消费 DOC-12 的 API,避免业务页面与 Observability 数据混淆。

#### 设计决策(ADR)

- **ADR-108(Admin Obs 面板独立)**:DOC-11 v4 原 Task 11.4 的"Admin 面板"只负责业务管理(用户/邀请码/审计日志);Observability 相关 UI(Harness 分析、Entropy 告警、Grafana 跳转)拆到独立的 Task 11.6。来源:Batch 5 §B5-II。

#### 页面结构

路由:`/admin/observability`,admin 角色独占。

子 Tab:
1. **Harness Analytics**(默认) — 汇总卡 + 信号分布 + runs 列表 + harness_summary 详情
2. **Entropy Alerts** — 告警列表 / 过滤 / 确认 / 历史
3. **External Dashboards** — Grafana 外链 + OTel Traces 查询入口

#### 子 Tab 详情

**Harness Analytics**:
- 汇总卡:24h runs / guardrail_triggers / permission_denies / compaction_count / mean_turn_count / cache_hit_ratio
- 信号分布柱状图(按 harness_event subtype 24h 计数)
- 最近 20 个 runs 列表:点击展开 `runs.harness_summary` 详情(middleware_count / failure_types 分布)
- 数据源:`GET /admin/stats/dashboard`(DOC-09 v4) + `GET /admin/audit-logs?action=harness.*`

**Entropy Alerts**:
- 告警列表:按时间倒序,每条含 severity / signal_type / detail / acknowledged_at
- 过滤器:severity / signal_type / 时间范围
- 确认按钮:POST `/admin/entropy/alerts/{id}/acknowledge`(DOC-12 v4 Task 12.8)
- 历史视图:已确认告警

**External Dashboards**:
- Grafana 链接 4 个 dashboard(DOC-12 v4 Task 12.4 的 4 套 JSON 配置):
  - `http://localhost:3001/d/prism-overview` — Runs/s, Errors/s, P95
  - `http://localhost:3001/d/prism-harness` — guardrail/permission/hook 时序
  - `http://localhost:3001/d/prism-models` — tokens/cost/cache
  - `http://localhost:3001/d/prism-agents` — 子进程/fork/background 生命周期
- OTel 链接:跳到 Jaeger/Tempo(部署时配置 URL)

### Part B — 实现规范

```
frontend/src/
├── app/admin/observability/
│   ├── page.tsx                      # 容器 + Tab 切换
│   ├── harness-analytics/page.tsx
│   ├── entropy-alerts/page.tsx
│   └── external-dashboards/page.tsx
├── features/observability/
│   ├── HarnessAnalyticsPanel.tsx
│   ├── HarnessSignalDistributionChart.tsx
│   ├── HarnessSummaryDrawer.tsx
│   ├── EntropyAlertsList.tsx
│   ├── EntropyAlertFilters.tsx
│   ├── GrafanaLinks.tsx
│   ├── use-admin-stats.ts
│   ├── use-entropy-alerts.ts
│   └── observability-api.ts
```

## 验证步骤

```bash
npx tsc --noEmit
npx playwright test admin-observability.spec.ts
# 桌面 1280x800 + 移动 375x812
# 测试:Harness Analytics 加载汇总卡 / Entropy Alerts 确认流程 / Grafana 外链正确拼接
```

## 完成后

1. 更新 PROGRESS.md:Task 11.6 完成
2. `git add -A && git commit -m "feat(v4): admin observability panel (harness analytics + entropy alerts + grafana links)"`

---

## 附录 A: v4 修订清单

本次修订共 22 处精确修补,对应 Batch 1-5 review + PDF 补丁 + Master + UI design spec:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,Task 数 4 → 6,v4 摘要段,Poco 功能 vs 体积审计点 | 全局 |
| 2 | **Task 11.1 扩充(Chat 界面)** | ChatHeader 双态布局(桌面/移动)对齐 UI design spec §6 + permission_ask 弹窗 + coordinator plan 可视化 + run_crashed 恢复提示;ADR-100/ADR-101 | Batch 4 §B4-3, §B4-I |
| 3 | Task 11.1 ChatHeader 双态 | 对齐 UI design spec §6 | Batch 4 §B4-I |
| 4 | **Task 11.2 扩充(Session 管理)** | export/import / share(只读链接) / fork / archive / tag / 多选批量;ADR-102 | Batch 4 §C-1 |
| 5 | **Task 11.3 扩充(IM 绑定 UX)** | 完整配对码流程:生成 → 倒计时 → 二维码 → SSE 检测 → 成功展示 → 解绑;ADR-103 | Batch 4 §C-1 |
| 6 | **Task 11.4 扩充(用量仪表盘)** | 汇总卡加 Cache 命中率 + cache 节省金额 + 按 Provider 饼图(分层 cache tokens 三字段)+ 趋势折线双轴(cost + cache_hit_ratio);ADR-104 | Batch 4 §C-1, Master M7 |
| 7 | **Task 11.5 大幅修订(拆 3 页)** | 原 Task 11.5 拆为:`/skills`(Skills Store)/ `/plugins/create`(Plugin Builder)/ `/settings/harness`(Harness Config 只读) | Master M8, Batch 4 §C-1 |
| 8 | Task 11.5 Skills Store | ADR-105:源筛选只显示 Local + GitHub(两源,Phase 1) | Master M8 |
| 9 | Task 11.5 Plugin Builder | ADR-106:对话式 UI + **实时完整度进度条**(7 维度评分)+ 右侧 PluginStructureTree;阈值 0.8 时"生成"按钮激活 | Batch 4 §C-1, DOC-04 v4 ADR-038 |
| 10 | Task 11.5 Harness Config | ADR-107:只读展示(DB 层 + 默认层)+ source_trace 显示字段来自哪一源;v4 无任何 input 可编辑,只能重启服务改 yaml | Master M8, DOC-03 v4 ADR-031 |
| 11 | **Task 11.6 新增(Admin Obs 面板)** | ADR-108:从 DOC-11 独立,专职消费 DOC-12 v4 的 API;3 个子 Tab:Harness Analytics / Entropy Alerts / External Dashboards | Batch 5 §B5-II |
| 12 | Task 11.6 Harness Analytics 面板 | 汇总卡 + 信号分布 + runs 列表 + harness_summary 详情抽屉 | Batch 5 §B5-I |
| 13 | Task 11.6 Entropy Alerts 面板 | 告警列表 / 过滤 / 确认(POST acknowledge)/ 历史 | Batch 5 §B5-IV |
| 14 | Task 11.6 Grafana 链接 | 外链到 localhost:3001 的 4 套 dashboard(DOC-12 v4 Task 12.4 `prism-overview / prism-harness / prism-models / prism-agents`)+ OTel Traces | Batch 5 §B5-V |
| 15 | 所有 Task 组件实现 | 扩充 Part B 实现规范(补完骨架)复用 DOC-10 v4 基础组件 | Batch 4 §B4-1 |
| 16 | Playwright E2E 测试 | 每个 Task 必带 desktop + mobile 双视口 E2E 脚本样例 | UI design spec, Batch 4 §B4-V |
| 17 | Poco 功能保留 vs 体积 | 明文说明:参考 Poco 68 文件架构完整保留功能,但不 fork 代码(体积 <10MB) | Batch 4 §B4-5 |
| 18 | 结构化日志/错误上报 | 前端关键操作 → `POST /frontend-errors`(DOC-10 v4 ADR-095) | Batch 5 §B5-I |
| 19 | ADR 编号 ADR-100~108 + 交叉引用 v3 → v4 | 全局 | 全局 |
| 20 | Observability 采集说明 | 加 Web Vitals / 首 token 延迟 / Cache 命中率前端埋点 | Batch 5 §B5-I |
| 21 | Task 11.4 Admin 面板保留但精简 | 用户/邀请码/审计日志管理 留在 11.4;Observability 拆到 11.6 | Batch 5 §B5-II |
| 22 | 附录 A + 文末 | 修订清单 + 下一步 DOC-12 v4 | SOP |

---

> **文档维护说明(v4)**:本文档的 6 个 Task 完成后,Prism v2 将拥有完整的前端功能:对话界面(**streaming + 工具卡片 + Harness 通知 + permission_ask 弹窗 + coordinator plan 可视化 + run_crashed 恢复**)+ 会话管理(**含 export/import/share/fork/archive/tag/多选批量**)+ 设置页面(Provider/MCP/**IM 完整配对流程**)+ 用量仪表盘(**Cache 命中率 + 节省金额 + Provider 饼图分层 + 趋势双轴**)+ **Skills Store / Plugin Builder(完整度进度条) / Harness Config(只读 + source_trace)3 个独立子页** + **Admin Observability 面板**(Harness Analytics + Entropy Alerts + Grafana 外链)。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-12 v4 Observability & Entropy
