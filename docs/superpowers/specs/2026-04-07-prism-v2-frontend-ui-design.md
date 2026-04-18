# Prism v2 — Frontend UI Design Spec

> **文档编号**: DESIGN-UI-01
> **版本**: 1.0
> **日期**: 2026-04-07
> **性质**: UI/UX 设计规格 — 全部前端页面视觉与交互定义
> **前置依赖**: DOC-10（前端基础架构）, DOC-11（前端功能）, Poco 前端架构审计
> **参考来源**: Claude.ai DESIGN.md (VoltAgent/awesome-design-md), Poco-Claw Frontend (424 files)

---

## 目录

1. [设计哲学](#1-设计哲学)
2. [设计 Token 系统](#2-设计-token-系统)
3. [字体系统](#3-字体系统)
4. [主题系统](#4-主题系统)
5. [全局布局架构](#5-全局布局架构)
6. [对话页面](#6-对话页面)
7. [Agent Panel（右侧面板）](#7-agent-panel)
8. [侧边栏](#8-侧边栏)
9. [TaskComposer（输入区）](#9-taskcomposer)
10. [Capabilities Platform（能力平台）](#10-capabilities-platform)
11. [设置页面](#11-设置页面)
12. [用量仪表盘与 Admin 面板](#12-用量仪表盘与-admin-面板)
13. [状态 UI 规范](#13-状态-ui-规范)
14. [组件设计规范](#14-组件设计规范)
15. [响应式与移动端](#15-响应式与移动端)
16. [动效规范](#16-动效规范)
17. [无障碍与国际化](#17-无障碍与国际化)

---

## 1. 设计哲学

### 核心定位

Prism 是一个 **Agent 运行平台**，视觉风格对标 Claude.ai：**英式典雅庄重、暖色调、大量留白、衬线标题体现权威感**，但不会给用户带来压迫感。

### 设计原则

| 原则 | 说明 |
|------|------|
| **Warm Neutrals** | 所有灰色带黄棕暖色调，没有冷灰。Claude 的核心特征 |
| **Serif for Authority, Sans for Utility** | 衬线标题传递庄重感，无衬线正文保证易读性 |
| **Progressive Complexity** | 日常对话时极简，Agent 执行时展示全部信息。双态视觉密度 |
| **Ring Shadows** | 用 `0 0 0 1px` ring shadow 代替传统 drop shadow，Claude 签名手法 |
| **Editorial Rhythm** | 大量留白、section 间 80-120px 间距、内容区居中 max-w-3xl |
| **State-Driven Layout** | 布局变化由系统状态（run status）驱动，不猜测用户意图 |

### UI 范式

**Chat-Centric + 状态驱动 Agent Panel**

- 基础体验 = Claude.ai 全宽对话
- Agent 运行时 = 自动展开右侧 Agent 详情面板
- 参考 Poco 的组件结构和功能布局，数据层完全基于 Prism SSE 事件模型

---

## 2. 设计 Token 系统

### 颜色 Token（语义化）

```css
/* === 共享 Base Tokens（三套主题通用）=== */

/* 品牌色 */
--color-brand:            #c96442;   /* Terracotta — 主 CTA、重点链接 */
--color-brand-hover:      #d97757;   /* Coral — hover 态 */
--color-brand-muted:      #c9644220; /* 低饱和背景色 */

/* 状态色（暖色系，不破坏整体典雅感）*/
--color-success:          #2D5F4A;   /* 暗绿 — 完成态 */
--color-success-muted:    #2D5F4A15;
--color-warning:          #B8860B;   /* 琥珀暖黄 — guardrail 触发 */
--color-warning-muted:    #B8860B15;
--color-error:            #8B3A4A;   /* 暗红 — 失败/circuit break */
--color-error-muted:      #8B3A4A15;
--color-info:             #4A6FA5;   /* 静谧蓝 — 信息提示 */
--color-info-muted:       #4A6FA515;

/* 焦点 */
--color-focus-ring:       #3898ec;   /* Focus Blue — 唯一的冷色，仅 focus 态 */

/* 间距基准 */
--spacing-unit:           8px;
--spacing-xs:             4px;
--spacing-sm:             8px;
--spacing-md:             16px;
--spacing-lg:             24px;
--spacing-xl:             32px;
--spacing-2xl:            48px;
--spacing-3xl:            64px;
--spacing-section:        96px;      /* section 间距 */

/* 圆角（对齐 Claude DESIGN.md 7 档刻度） */
--radius-sharp:           4px;       /* 内联小元素 */
--radius-subtle:          6px;       /* 小按钮、次要交互 */
--radius-md:              8px;       /* 标准按钮、卡片 */
--radius-lg:              12px;      /* 主按钮、输入框、导航 */
--radius-xl:              16px;      /* 特色容器、视频播放器 */
--radius-2xl:             24px;      /* 标签元素、高亮容器 */
--radius-3xl:             32px;      /* Hero 容器、嵌入媒体 */
--radius-full:            9999px;    /* pill */

/* 深度系统 — 5 级（对齐 Claude DESIGN.md）
 * Level 0 Flat:      无阴影无边框（Parchment 背景、内联文字）
 * Level 1 Contained: 1px solid border（标准卡片、section）
 * Level 2 Ring:      0 0 0 1px ring shadow（交互卡片、按钮、hover）
 * Level 3 Whisper:   极柔 drop shadow（浮层、产品截图）
 * Level 4 Inset:     inset ring（active/pressed）
 */
--shadow-ring:            0 0 0 1px var(--color-ring);
--shadow-ring-hover:      0 0 0 1px var(--color-ring-deep);
--shadow-ring-focus:      0 0 0 2px var(--color-focus-ring);
--shadow-whisper:         0 4px 24px rgba(0,0,0,0.05);
--shadow-inset:           inset 0 0 0 1px rgba(0,0,0,0.15);
```

### 主题变量（仅换 6 个表面色）

```css
/* === Light 主题 === */
:root[data-theme="light"] {
  --color-surface:        #ffffff;
  --color-surface-raised: #fafafa;
  --color-surface-button: #f0f0ee;   /* 淡灰暖 — 次要按钮 */
  --color-text:           #141413;   /* Anthropic Near Black */
  --color-text-secondary: #5e5d59;
  --color-text-tertiary:  #87867f;
  --color-text-link:      #3d3d3a;
  --color-border:         #e5e5e5;
  --color-border-strong:  #d1d1d1;
  --color-ring:           #d1d1d1;
  --color-ring-deep:      #c0c0c0;
}

/* === Prism 主题（默认）=== */
:root[data-theme="prism"] {
  --color-surface:        #f5f4ed;   /* Parchment — 主画布 */
  --color-surface-raised: #faf9f5;   /* Ivory — 卡片/浮层 */
  --color-surface-button: #e8e6dc;   /* Warm Sand — 次要按钮背景（Claude 签名） */
  --color-text:           #4d4c48;   /* Charcoal Warm — 主文字 */
  --color-text-secondary: #5e5d59;   /* Olive Gray — 正文次要 */
  --color-text-tertiary:  #87867f;   /* Stone Gray — 脚注/元信息 */
  --color-text-link:      #3d3d3a;   /* Dark Warm — 深色文字链接 */
  --color-border:         #f0eee6;   /* Border Cream — 标准轻边框（最淡） */
  --color-border-strong:  #e8e6dc;   /* Border Warm — 突出边框/分割线 */
  --color-ring:           #d1cfc5;   /* Ring Warm — 按钮 hover/focus ring */
  --color-ring-deep:      #c2c0b6;   /* Ring Deep — active/pressed ring */
}

/* === Dark 主题 === */
:root[data-theme="dark"] {
  --color-surface:        #141413;   /* Near Black — 页面背景 */
  --color-surface-raised: #30302e;   /* Dark Surface — 卡片/浮层 */
  --color-surface-button: #30302e;   /* 暗色次要按钮 */
  --color-text:           #faf9f5;   /* Ivory */
  --color-text-secondary: #b0aea5;   /* Warm Silver */
  --color-text-tertiary:  #87867f;   /* Stone Gray */
  --color-text-link:      #b0aea5;   /* Warm Silver */
  --color-border:         #30302e;   /* Border Dark */
  --color-border-strong:  #424240;
  --color-ring:           #424240;
  --color-ring-deep:      #505050;
  --color-brand:          #d97757;   /* Coral — Dark 模式稍亮 */
}
```

---

## 3. 字体系统

### 分层加载策略

| Layer | 字体 | 加载方式 | 大小 |
|-------|------|---------|------|
| **0（立即）** | Georgia, system-ui, ui-monospace | 系统字体 | 0KB |
| **1（异步）** | Noto Sans SC | Google Fonts 动态子集 | ~200KB |
| **2（可选）** | Noto Serif SC | 设置中开启 | ~800KB |
| **3（按需）** | Noto Sans JP, Noto Sans KR | 检测到对应语言时加载 | 各 ~200KB |

### 字体栈定义

```css
--font-heading: "Noto Serif SC", Georgia, "Times New Roman", serif;
--font-body:    "Noto Sans SC", system-ui, -apple-system, "Segoe UI", sans-serif;
--font-code:    "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, monospace;
```

### 字体层级

| 角色 | 字体 | 大小 | 字重 | 行高 |
|------|------|------|------|------|
| Display | heading | 48px | 500 | 1.10 |
| H1 | heading | 36px | 500 | 1.20 |
| H2 | heading | 28px | 500 | 1.25 |
| H3 | heading | 22px | 500 | 1.30 |
| Body Large | body | 18px | 400 | 1.60 |
| Body | body | 16px | 400 | 1.60 |
| Body Small | body | 14px | 400 | 1.50 |
| Caption | body | 12px | 400 | 1.40 |
| Label | body | 12px | 500 | 1.25 |
| Code | code | 14px | 400 | 1.60 |

### 关键规则

- 衬线标题统一 weight 500，不用 bold (700+)
- 正文 line-height 1.60 保持 Claude 的宽松阅读感
- 中文标题间距 `letter-spacing: 0.05em`
- `max-w-[65ch]` 控制段落宽度

---

## 4. 主题系统

### 三套主题

| 主题 | 定位 | 默认 |
|------|------|------|
| **Prism** | 品牌特色，暖色 Parchment，英式典雅 | ✅ 是 |
| **Light** | 纯白底，干净专业 | |
| **Dark** | 深色，夜间/沉浸模式 | |

### 实现方式

- `<html data-theme="prism|light|dark">`
- CSS 变量覆盖，共享 base tokens
- 使用 `next-themes` 管理（同 Poco）
- 支持 `system` 自动跟随 OS（仅 Light/Dark 二选一，Prism 需手动选择）

### 主题切换位置

- 侧边栏底部图标按钮
- 设置页面 → 外观

---

## 5. 全局布局架构

### 页面地图

```
/                           → 重定向到 /chat
/chat                       → 新会话
/chat/[sessionId]           → 继续会话
/capabilities               → 能力平台主页
  /capabilities/skills      → Skills 管理 + 市场
  /capabilities/plugins     → Plugins 管理
  /capabilities/mcp         → MCP Server 管理
  /capabilities/commands    → Slash Commands 管理
  /capabilities/agents      → Sub Agents 管理
  /capabilities/env-vars    → 环境变量管理
  /capabilities/personalize → 个性化指令 / CLAUDE.md
/settings                   → 设置主页
  /settings/providers       → Provider 管理
  /settings/im              → IM 绑定
  /settings/harness         → Harness 配置
/usage                      → 用量仪表盘
/skills                     → Skills 商店（公开浏览）
/plugins/create             → 插件创建向导
/admin                      → Admin 面板
  /admin/users
  /admin/invites
  /admin/audit
/login                      → 登录
/register                   → 注册
```

### App Shell 结构

```
┌──────────────────────────────────────────────────┐
│ <html data-theme="prism">                        │
│ ┌──────────┬─────────────────────────────────┐   │
│ │          │                                 │   │
│ │ Sidebar  │  <SidebarInset>                 │   │
│ │ 280px    │    Main Content Area             │   │
│ │          │    (各页面路由)                   │   │
│ │          │                                 │   │
│ │          │                                 │   │
│ └──────────┴─────────────────────────────────┘   │
│ Toaster (sonner)                                 │
│ SettingsDialog (全局)                             │
└──────────────────────────────────────────────────┘
```

- 使用 shadcn/ui 的 `SidebarProvider` + `Sidebar` + `SidebarInset`
- 侧边栏桌面端固定 280px，`collapsible="icon"` 支持收起到 48px
- 移动端侧边栏 = left drawer（hamburger 按钮触发）

---

## 6. 对话页面

### 核心布局

对话页面是 Prism 最重要的界面，有两种视觉态：

**对话态（Agent 空闲）：**

```
┌──────────────────────────────────────────┐
│ ChatHeader                               │
│  Session 标题(serif)  Model▾  Agent▾  ⚡ │
├──────────────────────────────────────────┤
│                                          │
│         MessageList                      │
│         max-w-3xl 居中                   │
│         gap-6 宽松间距                   │
│                                          │
│  ┌────────────────────────────┐          │
│  │ 👤 UserMessage              │          │
│  └────────────────────────────┘          │
│  ┌────────────────────────────┐          │
│  │ 🤖 AssistantMessage         │          │
│  │    Markdown 渲染            │          │
│  └────────────────────────────┘          │
│                                          │
├──────────────────────────────────────────┤
│ TaskComposer (完整版)                    │
│ [textarea] [Mode▾] [📎] [MCP] [/] [Send]│
└──────────────────────────────────────────┘
```

**执行态（Agent 运行中）：**

```
┌──────────────────────────────────────────────────┐
│ ChatHeader                          ⚡ Harness OK │
├────────────────────────────┬─────────────────────┤
│                            │ Agent Panel (360px)  │
│  MessageList               │ ┌─────────────────┐ │
│  max-w-2xl                 │ │ [Steps][Tools]   │ │
│  gap-3 收紧间距            │ │ [Harness][Files] │ │
│                            │ ├─────────────────┤ │
│  👤 启动 Coordinator       │ │ ✓ Step 1        │ │
│  🤖 正在执行...            │ │ ● Step 2 ←当前  │ │
│     🔧 search_code ✓ 120ms│ │ ○ Step 3        │ │
│     🔧 edit_file ● ...    │ │                 │ │
│     ⚡ guardrail(inline)   │ │ 🔧 Tool Detail  │ │
│                            │ │  input: {...}   │ │
│                            │ │  output: {...}  │ │
│                            │ │  duration: 120ms│ │
├────────────────────────────┤ │                 │ │
│ TaskComposer (精简版)      │ │ ⚡ Harness       │ │
│ [input] [Send]             │ │  2 rules active │ │
└────────────────────────────┴─────────────────────┘
```

### 状态驱动规则

```typescript
// 面板展开逻辑
const [panelOpen, setPanelOpen] = useState(false);

useEffect(() => {
  if (runStatus === 'running') setPanelOpen(true);
  // run 完成时不自动关闭，保持面板供用户查看
}, [runStatus]);

// 用户可手动切换
// 点 X 关闭，点侧边按钮打开
```

### 双态视觉密度（CSS 实现）

```css
/* 对话态（默认） */
.message-list { max-width: 48rem; gap: 1.5rem; }
.tool-card    { padding: 12px 16px; }

/* 执行态（Agent Panel 展开时） */
[data-panel-open] .message-list { max-width: 42rem; gap: 0.75rem; }
[data-panel-open] .tool-card    { padding: 8px 12px; }
[data-panel-open] .composer     { /* 精简版 */ }
```

### 消息组件

| 组件 | 说明 |
|------|------|
| **UserMessage** | 右对齐（暖灰背景），支持附件预览 |
| **AssistantMessage** | 左对齐（白/ivory 背景），Markdown 渲染，streaming 打字效果 |
| **ToolChain** | 内联折叠卡片：图标 + 工具名 + 耗时/状态。点击展开 Agent Panel 对应 Tool 详情 |
| **HarnessNotice** | 内联 badge（guardrail=琥珀黄, permission_deny=暗红, compaction=灰色, loop=琥珀黄） |
| **PlanApprovalCard** | Plan Mode 审批卡片（Approve/Reject 按钮），内联在对话流中 |
| **UserInputRequestCard** | AskUserQuestion 等待卡片（60s 倒计时），选项按钮 |
| **RunStatusBar** | Run 完成后：状态 + token 用量 + 成本 + harness 摘要 |
| **PendingMessagesList** | 排队消息预览条（Composer 上方，Session 队列可视化） |
| **TypingIndicator** | 三点脉冲动画（Claude 风格） |

### Tool Chain 图标体系（参考 Poco）

| 工具类型 | 图标 | 颜色 |
|---------|------|------|
| Browser / Playwright | AppWindow | info |
| Memory | Brain | brand |
| MCP Server | Server | info |
| Skill | Sparkles | brand |
| Bash / Terminal | SquareTerminal | text-secondary |
| File Read | FileText | text-secondary |
| File Edit | Pencil | warning |
| Search / Glob | Search | text-secondary |
| Web Fetch | Globe | info |
| User Input | MessageSquare | brand |
| Task / Agent | Bot | brand |
| Notebook | Notebook | text-secondary |

状态：Running = spinner(text-secondary)，Completed = CheckCircle2(success)，Failed = XCircle(error)

---

## 7. Agent Panel（右侧面板）

### 结构

宽度 360px，`react-resizable-panels` 支持拖拽调整。

```
┌─────────────────────┐
│ Agent Activity    ✕  │
├─────────────────────┤
│ [Steps] [Tools]     │
│ [Harness] [Files]   │
├─────────────────────┤
│                     │
│ (标签页内容)         │
│                     │
│                     │
└─────────────────────┘
```

### 四个标签页

**Steps（步骤）：**
- Coordinator 模式下显示步骤列表
- 左侧竖线连接（`border-left: 2px solid var(--color-brand)`）
- 状态：✓ 完成 / ● 执行中(brand 脉冲) / ○ 待执行(tertiary)
- 单轮 Agent 不显示此标签

**Tools（工具详情）：**
- 当前 Run 所有工具调用列表
- 展开显示：input JSON、output JSON、duration、is_error
- 语法高亮（highlight.js）

**Harness（治理）：**
- 活跃规则列表（guardrail、middleware）
- 事件时间线：触发记录按时间排列
- 每条记录：时间戳 + subtype + detail 摘要

**Files（文件变更）：**
- Agent 修改的文件列表
- 每个文件：文件名 + 变更类型（created/modified/deleted）+ diff 摘要
- Phase 1 可简化为列表展示，不做 inline diff

### 面板背景

比主区域暗一档，制造层次感：

```css
.agent-panel {
  background: color-mix(in oklch, var(--color-surface) 92%, black);
  border-left: 1px solid var(--color-border);
}
```

---

## 8. 侧边栏

### 结构（参考 Poco MainSidebar）

```
┌──────────────────┐
│ 🔷 Prism    [+]  │  ← Logo + 新建会话按钮
├──────────────────┤
│ [🔍 搜索...]     │  ← Cmd+K 全局搜索
├──────────────────┤
│ ⭐ 置顶           │
│  · 会话 A         │
│  · 会话 B         │
├──────────────────┤
│ 📁 项目           │  ← 可折叠 + DnD 拖拽
│ ├ 项目 Alpha      │
│ │ ├ 会话 1        │
│ │ └ 会话 2        │
│ └ 项目 Beta       │
│   └ 会话 3        │
├──────────────────┤
│ 📋 历史           │  ← 按时间分组
│  今天              │
│   · 会话 X        │
│  昨天              │
│   · 会话 Y        │
│  更早              │
│   · 会话 Z        │
├──────────────────┤
│ ⚙ 设置  🌓 主题   │  ← 底部固定
│ 🧩 能力  👤 账户   │
└──────────────────┘
```

### 会话项（SessionItem）

- 标题（单行省略）
- 最后消息预览（单行，text-tertiary）
- 时间戳（相对时间）
- 右键菜单：重命名 / 置顶 / 移至项目 / 删除

### 交互

- **DnD**：`@dnd-kit` 拖拽会话到不同项目
- **置顶**：`is_pinned` + `pinned_at` 排序
- **搜索**：`Cmd+K` 打开 `cmdk` 命令面板（全局搜索会话 + 命令）
- **批量操作**：长按进入选择模式，批量删除/移动
- **收起**：`Ctrl+B` 收起到 48px 图标模式

---

## 9. TaskComposer（输入区）

### 完整版（对话态）

参考 Poco `task-composer/`，但用 Claude 视觉风格。

```
┌─────────────────────────────────────────────────┐
│ [PendingMessages: 排队 2 条 — 点击查看]          │  ← 仅队列非空时显示
├─────────────────────────────────────────────────┤
│                                                 │
│  textarea (自动高度, max-h-200px)                │
│  placeholder: "给 Prism 发消息..."               │
│                                                 │
├─────────────────────────────────────────────────┤
│ [Normal▾] [📎 附件] [🔌 MCP] [/ 命令]    [发送] │
│                                                 │
│ Mode: Normal | Plan | Scheduled                  │
│ 快捷键: Enter=发送, Shift+Enter=换行             │
│         Ctrl+Shift+P=切换 Plan Mode              │
└─────────────────────────────────────────────────┘
```

### 精简版（执行态）

Agent 运行中时，输入区收缩为单行：

```
┌─────────────────────────────────────────────────┐
│ [input: 追加消息到队列...]              [发送]   │
└─────────────────────────────────────────────────┘
```

### 模式说明

| 模式 | 说明 |
|------|------|
| **Normal** | 直接执行，默认模式 |
| **Plan** | 两阶段：先规划（只允许读操作）→ 用户审批 → 再执行 |
| **Scheduled** | 选择执行时间，写入定时任务 |

### Slash 命令补全

输入 `/` 触发下拉补全列表。命令来源：
- 系统内置（`/clear`, `/help`, `/settings`）
- 用户自定义（Capabilities → Slash Commands 管理）
- Skills 提供的命令

---

## 10. Capabilities Platform（能力平台）

### 整体结构（参考 Poco 68 文件架构，完整保留）

```
/capabilities
├── 左侧导航 (CapabilitiesSidebar)
│   ├── Skills
│   ├── Plugins
│   ├── MCP Servers
│   ├── Slash Commands
│   ├── Sub Agents
│   ├── Env Vars
│   └── Personalization
│
└── 右侧内容区 (CapabilityContentShell)
    ├── 头部: 搜索 + 新建按钮
    └── 内容: 卡片网格 / 列表
```

### 子模块规格

#### 10.1 Skills

**Skills 列表页：**
- 卡片网格展示（SkillsGrid）
- 每张卡片：名称、描述、来源图标（本地/GitHub/市场）、启用/禁用开关
- 搜索栏 + 来源筛选

**Skills 市场浏览（SkillMarketplaceBrowser）：**
- 对接 DOC-05 Task 5.5~5.6 Skills Market API
- 搜索 + 分页 + 源筛选（Manus/npm/GitHub/已安装）
- 安装确认弹窗（权限声明、来源说明）
- 版本历史、README 预览（SkillDetailDrawer）

**Skills 设置弹窗（SkillSettingsDialog）：**
- 启用/禁用
- 配置覆盖
- 卸载 + 更新

#### 10.2 Plugins

结构同 Skills：列表 + 导入（GitHub URL）+ 设置弹窗。
额外：`/plugins/create` 路由导向 PluginBuilder 向导页。

#### 10.3 MCP Servers

**MCP 卡片网格（McpGrid）：**
- 每张卡片：服务器名、命令、状态指示灯（connected/disconnected/error）
- 连接/断开按钮

**MCP 设置弹窗（McpSettingsDialog）：**
- Name（唯一性校验）
- Command + Args
- 环境变量（key-value 编辑器）
- 连通性测试按钮

#### 10.4 Slash Commands

- 命令列表（SlashCommandsList）
- 新建/编辑弹窗（name, description, prompt template）
- 补全建议状态管理（供 TaskComposer 使用）

#### 10.5 Sub Agents

- 子代理列表（SubAgentsList）
- 新建/编辑弹窗：名称、描述、System Prompt、可用工具列表勾选
- 对接 DOC-04 Coordinator 子代理配置

#### 10.6 Env Vars

- 环境变量卡片网格（EnvVarsGrid）
- 添加弹窗（key, value with masked display, scope: global/project）
- 变量注入到 Executor 运行时环境

#### 10.7 Personalization

- 自定义指令编辑器（Markdown textarea）
- CLAUDE.md 管理（项目级 + 全局级）
- 预览效果

#### 10.8 Harness Config（从 Settings 移至 Capabilities）

- Guardrail 规则列表（启用/禁用/编辑/添加）
- Middleware 开关面板
- 权限策略编辑器
- 配置来源追踪（每条配置标注来自哪个源）

---

## 11. 设置页面

### 结构（参考 Poco SettingsDialog）

桌面端 = Modal Dialog，移动端 = Bottom Sheet（drag handle）。

### 标签页

| 标签 | 内容 |
|------|------|
| **账户** | 头像、用户名、手机号、邀请码使用情况、登出 |
| **Provider** | LLM Provider 列表 + 新增/编辑/删除 + API Key 管理 + 连通性测试 |
| **IM 绑定** | Telegram/钉钉/飞书 绑定列表 + 配对码生成 + 解绑 |
| **外观** | 主题切换（Prism/Light/Dark）、字体设置（衬线中文标题开关）、语言切换 |
| **快捷键** | 键盘快捷键参考表 |

### Provider 管理

- Provider 卡片：名称 + 健康状态灯 + API Key（掩码） + 测试按钮
- 新增支持预设选择（OpenAI/Anthropic/MiniMax/自定义）
- API Key 输入：`sk-` 前缀校验，密码模式
- Base URL：格式校验，可选

---

## 12. 用量仪表盘与 Admin 面板

### 用量仪表盘（/usage）

- **汇总卡片**：总 Runs、总 Tokens、总成本（4 列网格）
- **趋势图**：按日/周/月的 token 用量折线图（recharts）
- **Provider 饼图**：按 Provider 分布
- **最近 Runs 列表**：状态 + 时间 + token + 成本 + harness_summary 摘要

数据来源：`GET /providers/usage` API，前端不做本地计算。

### Admin 面板（/admin，admin only）

| 页面 | 内容 |
|------|------|
| **概览** | 全局用量统计（所有用户汇总） |
| **用户管理** | 用户列表（搜索/角色/状态）+ 详情 |
| **邀请码** | 邀请码列表 + 生成 + 使用统计 |
| **审计日志** | 日志查看器 + action 前缀筛选（`user.*`, `harness.*`）+ 分页 |

---

## 13. 状态 UI 规范

全局统一，所有页面遵守：

| 状态 | 展示方式 |
|------|---------|
| **Loading** | 骨架屏（Skeleton），匹配实际布局尺寸。不用 spinner |
| **Empty** | 居中插图 + 引导文案 + 操作按钮（"创建第一个..."） |
| **Error** | 内联错误提示 + 重试按钮。不用全屏错误页 |
| **Offline** | 顶部横幅"网络连接已断开"，灰色覆盖交互区域 |
| **Streaming** | 打字光标脉冲（`▊` + blink 动画） |
| **Queued** | PendingMessagesList 显示排队计数 + 预览 |

---

## 14. 组件设计规范

### 按钮（Button）

**5 个核心 variant（对齐 Claude DESIGN.md）+ 2 个扩展：**

| Variant | 背景 | 文字 | Ring Shadow | 用途 |
|---------|------|------|-------------|------|
| **brand** (primary) | `--color-brand` (#c96442) | Ivory (#faf9f5) | `0 0 0 1px #c96442` | 主 CTA — 唯一带品牌色的按钮 |
| **warm-sand** (secondary) | `--color-surface-button` (#e8e6dc) | `--color-text` (#4d4c48) | `0 0 0 1px var(--color-ring)` | 次要操作 — Claude 最常用按钮 |
| **white** | #ffffff | `--color-text` (#141413) | none | 亮色表面上的清洁按钮 |
| **dark** | #30302e | Ivory (#faf9f5) | `0 0 0 1px #30302e` | 深色强调（light 主题上） |
| **ghost** | transparent | `--color-text-secondary` | none | 工具栏/图标按钮 |
| **destructive** | `--color-error` | white | none | 删除操作（扩展） |
| **link** | transparent | `--color-brand` | none | 文字链接（扩展） |

> **Claude 签名**：Warm Sand 是日常最高频按钮，Brand Terracotta 只用于最高优先级 CTA。

**尺寸**：default(h-9 px-12) / sm(h-8 px-8) / lg(h-10 px-16) / icon(36px) / icon-sm(32px)

**Padding 规则**：按钮带图标时使用不对称 padding `0px 12px 0px 8px`（图标侧更紧，Claude 签名手法）。

**交互**：
- Hover: ring shadow `var(--shadow-ring-hover)` + 微妙背景色 shift
- Active: `scale(0.98)` + `var(--shadow-inset)` 按压感
- Focus: `var(--shadow-ring-focus)` 2px focus ring

### 卡片（Card）

```css
/* Level 1 Contained — 标准卡片 */
.card {
  background: var(--color-surface-raised);        /* Ivory #faf9f5 */
  border: 1px solid var(--color-border);          /* Border Cream #f0eee6（最淡） */
  border-radius: var(--radius-md);                /* 8px */
}
/* Level 2 Ring — 交互态 */
.card:hover {
  box-shadow: var(--shadow-ring);                 /* 0 0 0 1px ring */
}
/* Level 3 Whisper — 浮层/特色卡片 */
.card-featured {
  box-shadow: var(--shadow-whisper);              /* 0 4px 24px rgba(0,0,0,0.05) */
  border-radius: var(--radius-xl);                /* 16px */
}
/* 不用传统 drop shadow — 深度通过 ring + 背景色层次表达 */
```

### 输入框（Input）

```css
.input {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);         /* 12px */
  padding: 8px 12px;
  color: var(--color-text);
}
.input:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--color-focus-ring);
}
```

### Toast 通知

使用 `sonner`，位置: bottom-right。样式覆盖为 Claude 暖色调：

| 类型 | 边框色 | 图标色 |
|------|--------|--------|
| success | `--color-success` | `--color-success` |
| error | `--color-error` | `--color-error` |
| warning | `--color-warning` | `--color-warning` |
| info | `--color-info` | `--color-info` |

### Badge

Harness 事件和状态标识用 badge：

```css
.badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
}
.badge-brand    { background: var(--color-brand-muted); color: var(--color-brand); }
.badge-success  { background: var(--color-success-muted); color: var(--color-success); }
.badge-warning  { background: var(--color-warning-muted); color: var(--color-warning); }
.badge-error    { background: var(--color-error-muted); color: var(--color-error); }
```

---

## 15. 响应式与移动端

### 策略：可用但不优化

桌面优先设计（自用 5-20 人场景），移动端保证可用。

### 断点

| 名称 | 宽度 | 变化 |
|------|------|------|
| mobile | < 768px | 单列，侧边栏→drawer，Agent Panel→bottom sheet |
| tablet | 768-1024px | 侧边栏可收起，Agent Panel 叠在对话上方 |
| desktop | 1024-1440px | 标准双栏 |
| wide | > 1440px | 三栏（侧边栏 + 对话 + Agent Panel 同时显示） |

### 移动端降级

| 桌面组件 | 移动端替代 |
|---------|-----------|
| Sidebar 280px | Left drawer (hamburger) |
| Agent Panel 360px | Bottom sheet (50vh) |
| TaskComposer toolbar | 收进 `···` 菜单，只露输入框 + 发送 |
| Settings Modal | Bottom sheet (drag handle) |
| 全局搜索 Modal | 全屏搜索页 |
| DnD 拖拽 | 长按 → 操作菜单 |

---

## 16. 动效规范

### 原则

- 动效服务于功能反馈，不是装饰
- 所有过渡用 custom cubic-bezier，不用 `linear` 或 `ease-in-out`
- 只动画 `transform` 和 `opacity`，保证 60fps

### 关键动效

| 元素 | 动效 | 时长 | 曲线 |
|------|------|------|------|
| Agent Panel 展开/收起 | width 过渡 | 300ms | `cubic-bezier(0.32, 0.72, 0, 1)` |
| 消息出现 | fade-up (`translate-y(8px)` → 0) | 200ms | ease-out |
| Streaming 光标 | blink | 1s | step-end |
| Tool Card 折叠/展开 | height + opacity | 200ms | ease-out |
| 侧边栏收起/展开 | width | 200ms | ease-out |
| Toast 进入 | slide-up + fade | 150ms | ease-out |
| Skeleton shimmer | gradient 移动 | 1.5s | linear (唯一例外) |
| 状态点脉冲（running） | scale + opacity | 1.5s | ease-in-out, infinite |
| Button press | scale(0.98) | 100ms | ease-out |

### 性能规则

- `backdrop-blur` 只用于 fixed/sticky 元素（导航栏、overlay）
- 不在滚动容器上加 blur/shadow
- 持续动画（shimmer、pulse）隔离到独立 client component，React.memo 包裹
- `will-change: transform` 仅在动画启动时添加，结束后移除

---

## 17. 无障碍与国际化

### 无障碍

| 规则 | 标准 |
|------|------|
| 颜色对比度 | 正文 ≥ 4.5:1 (WCAG AA)，大标题 ≥ 3:1 |
| 键盘导航 | 所有交互元素可 Tab 到达，Enter/Space 触发 |
| Focus visible | 2px focus ring（`--color-focus-ring`） |
| Screen reader | ARIA labels on icons, role on interactive elements |
| 触摸目标 | ≥ 44×44px（移动端） |
| Reduced motion | `prefers-reduced-motion: reduce` 时禁用所有动画 |

### 国际化

**语言优先级**：中文 > 英文 > 法语 > 西班牙语 > 阿拉伯语 > 韩语 > 日语

**实现**：
- `i18next` + URL 路径 `[lng]`（同 Poco）
- 翻译文件：`public/locales/{lng}/common.json`
- 日期/数字：`Intl.DateTimeFormat` + `Intl.NumberFormat`
- RTL 支持（阿拉伯语）：CSS `dir="rtl"` + logical properties（`margin-inline-start` 代替 `margin-left`）
- 字体按语言异步加载（Layer 3）

---

## 附录 A：技术栈确认

| 维度 | 选型 | 来源 |
|------|------|------|
| 框架 | Next.js 14+ (App Router) | PRD DOC-10 |
| UI 组件 | shadcn/ui (New York style) | PRD DOC-10 + Poco |
| 样式 | Tailwind CSS v4 | Poco 实践 |
| 状态（服务端） | TanStack React Query v5 | PRD DOC-10 |
| 状态（客户端） | Zustand（少量） | PRD DOC-10 |
| 表单 | React Hook Form + Zod | Poco 实践 |
| 图标 | Lucide React | Poco 实践 |
| 动画 | Motion (framer-motion) | Poco 实践 |
| 图表 | Recharts | PRD DOC-11 |
| 拖拽 | @dnd-kit | Poco 实践 |
| 命令面板 | cmdk | Poco 实践 |
| Toast | Sonner | Poco 实践 |
| 主题 | next-themes | Poco 实践 |
| i18n | i18next | Poco 实践 |
| Markdown | react-markdown + remark/rehype | Poco 实践 |
| 面板 | react-resizable-panels | Poco 实践 |

## 附录 B：Poco 组件参考映射

| Poco 组件 | Prism 对应 | 参考程度 |
|-----------|-----------|---------|
| `features/chat/` (95 files) | 对话页全部组件 | 视觉+结构参考，数据层重写 |
| `features/task-composer/` (24 files) | TaskComposer | 完整参考 |
| `features/capabilities/` (68 files) | Capabilities Platform | 完整参考 |
| `components/shell/sidebar/` | 侧边栏 | 完整参考 |
| `features/settings/` (18 files) | 设置页面 | 结构参考 |
| `features/home/` (14 files) | 首页 | 简化参考 |
| `features/projects/` (17 files) | 项目管理 | 完整参考 |
| `features/search/` (6 files) | 全局搜索 | 完整参考 |
| `features/scheduled-tasks/` (13 files) | 定时任务 | 完整参考 |
| `features/memories/` (5 files) | 记忆管理 | 完整参考 |
| `features/connectors/` (11 files) | 连接器 | 评估后决定 |
| `features/voice/` (4 files) | 语音输入 | Phase 2 |
| `features/onboarding/` (3 files) | 新手引导 | Phase 2 |
| `features/attachments/` (2 files) | 文件上传 | 完整参考 |
| `execution/computer-panel/` | — | 不实现（2C2G 限制） |
| `execution/replay/` | — | Phase 2 |

## 附录 C：DESIGN.md 参考来源

本设计 spec 的视觉方向基于以下 DESIGN.md 文件：

- **主参考**：`~/.claude/plugins/local/awesome-design-md/design-md/claude/DESIGN.md`
  - Parchment/Ivory 色系、Terracotta 强调色、Ring Shadow、衬线/无衬线层级
- **辅助参考**：
  - `linear.app/DESIGN.md` — 暗色模式参考
  - `stripe/DESIGN.md` — 专业严谨感
  - `notion/DESIGN.md` — 留白和排版节奏

## 附录 D：可用 Skills 清单

以下 Skills 已安装到项目，实现前端时可激活使用：

| Skill | 位置 | 用途 |
|-------|------|------|
| `frontend-design` | `.claude/skills/frontend-design/` | 阻止 AI slop，强制选定美学方向 |
| `taste-skill` | `.claude/skills/taste-skill/` | 161 条 UI 规则，覆盖排版/配色/间距/动效 |
| `soft-skill` | `.claude/skills/soft-skill/` | Awwwards 级视觉质量，$150k agency 级别 |
| `ui-ux-pro-max` | `.claude/plugins/local/ui-ux-pro-max-skill/` | 设计系统生成器，67 种风格 + 57 组字体 |
| `awesome-design-md` | `~/.claude/plugins/local/awesome-design-md/` | 54 个品牌 DESIGN.md 参考库（全局） |
