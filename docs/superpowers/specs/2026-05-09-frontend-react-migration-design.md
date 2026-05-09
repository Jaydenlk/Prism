# Prism Frontend: React + TypeScript + Vite Migration

> **Date**: 2026-05-09
> **Status**: Draft
> **Scope**: 全前端迁移 — 从 Prism.html 单文件 React (CDN) 到 Vite + React 18 + TypeScript 工程化项目

---

## 1. 背景与动机

### 当前状态
- `frontend/Prism.html` — 4500+ 行单文件，React 通过 CDN 加载，Babel 运行时编译
- `frontend/admin.html` — 900+ 行独立 Admin 面板
- `frontend/styles.css` — 1500 行设计系统（CSS Variables，editorial 风格）
- `frontend/apiClient.js` — API 客户端（auth、SSE、CRUD）

### 问题
1. **4500 行单文件不可持续** — 每加一个功能都在增加维护负债
2. **无类型系统** — 用户硬规则要求"类型严格，不使用 any"，当前 JS 无法满足
3. **无构建流程** — 无 tree-shaking、无 code splitting、无 lazy loading
4. **对标 Manus** — 商业级竞品要求组件化、可测试、可扩展的前端架构

### 决策
- **React + TypeScript + Vite**（不是 Next.js — Prism 是 SPA，不需要 SSR/SSG）
- **混合策略**：核心体验（Chat、Skills Market）重做；功能页面（Settings、Usage）提取+类型化
- **保留现有设计语言**：暖色调 / 衬线体 / editorial 风格，不重新设计视觉

---

## 2. 技术选型

| 选型 | 选择 | 理由 |
|---|---|---|
| 构建工具 | Vite 6.x | HMR 快、配置简、TS 原生支持 |
| UI 框架 | React 18.x | 现有代码已是 React，迁移成本最低 |
| 类型系统 | TypeScript strict | 用户硬规则 #3 |
| 路由 | React Router v6 | SPA 标准、lazy loading 支持 |
| 样式 | CSS Modules + CSS Variables | 保留现有 design tokens，加模块作用域 |
| 内容渲染 | marked + DOMPurify + Prism.js | Markdown→HTML 管线，语法高亮 |
| Markdown 导出 | Turndown.js | HTML→Markdown 反序列化 |
| 全局状态 | React Context + useReducer | 够用，不引入 Redux/Zustand（KISS） |
| 不引入 | Redux, Zustand, Tailwind, styled-components, Next.js | KISS 原则 |

---

## 3. 目录结构

```
frontend-react/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx                    # 入口
│   ├── App.tsx                     # Router + providers
│   ├── theme/
│   │   ├── tokens.ts              # 设计 token 常量
│   │   ├── global.css             # 全局样式 + CSS Variables
│   │   └── fonts.css              # 字体引入
│   ├── components/                 # 公共组件
│   │   ├── Button/
│   │   │   ├── Button.tsx
│   │   │   └── Button.module.css
│   │   ├── Icon/
│   │   │   └── Icon.tsx           # 35 个 SVG icon
│   │   ├── Modal/
│   │   ├── Toast/
│   │   ├── Badge/
│   │   ├── Spinner/
│   │   ├── Dropdown/
│   │   └── Layout/
│   │       ├── AppLayout.tsx      # Sidebar + Topbar + Main
│   │       ├── Sidebar.tsx
│   │       └── Topbar.tsx
│   ├── hooks/                      # 自定义 hooks
│   │   ├── useAuth.ts
│   │   ├── useApi.ts
│   │   ├── useSSE.ts
│   │   ├── useSessions.ts
│   │   └── useTheme.ts
│   ├── api/                        # API 层
│   │   ├── client.ts              # typed fetch wrapper
│   │   ├── auth.ts
│   │   ├── sessions.ts
│   │   ├── runs.ts
│   │   ├── skills.ts
│   │   ├── plugins.ts
│   │   ├── providers.ts
│   │   ├── admin.ts
│   │   └── types.ts               # API 响应类型
│   ├── pages/                      # 页面组件
│   │   ├── Auth/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── RegisterPage.tsx
│   │   │   └── MagicLinkCallback.tsx
│   │   ├── Chat/
│   │   │   ├── ChatPage.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── Composer.tsx
│   │   │   ├── ToolCard.tsx
│   │   │   ├── PermissionModal.tsx
│   │   │   ├── PlanPanel.tsx
│   │   │   └── ContentRenderer.tsx
│   │   ├── Sessions/
│   │   │   └── SessionsPage.tsx
│   │   ├── Settings/
│   │   │   ├── SettingsPage.tsx
│   │   │   ├── ProfileTab.tsx
│   │   │   ├── ProvidersTab.tsx
│   │   │   ├── McpTab.tsx
│   │   │   ├── ImTab.tsx
│   │   │   └── PreferencesTab.tsx
│   │   ├── Skills/
│   │   │   ├── SkillsPage.tsx
│   │   │   ├── SkillCard.tsx
│   │   │   └── SkillDetailPanel.tsx
│   │   ├── Plugins/
│   │   │   └── PluginBuilderPage.tsx
│   │   ├── Usage/
│   │   │   └── UsagePage.tsx
│   │   ├── Observability/
│   │   │   └── ObsPage.tsx
│   │   └── Admin/
│   │       ├── AdminLayout.tsx
│   │       ├── AdminDashboard.tsx
│   │       ├── UsersPage.tsx
│   │       ├── AuditPage.tsx
│   │       └── AdminProvidersPage.tsx
│   ├── context/                    # 全局状态
│   │   ├── AuthContext.tsx
│   │   ├── ThemeContext.tsx
│   │   └── SessionContext.tsx
│   └── utils/
│       ├── time.ts                # formatTime, groupByTime
│       ├── markdown.ts            # renderMarkdown, exportMarkdown
│       └── i18n.ts                # 国际化
```

---

## 4. 六阶段交付计划

### Phase 1: 基建（地基）

**目标**：项目可运行、设计系统可用、公共组件齐全

1. **Vite 项目搭建** — `npm create vite@latest`，TypeScript strict，path alias `@/`
2. **设计系统迁移** — 现有 `styles.css` 的 CSS Variables 提取为 `tokens.ts` 常量 + `global.css` 输出，双份同步
3. **Icon 系统** — 35 个 SVG → `Icon.tsx` typed component，`name` 属性有字面量类型约束
4. **公共组件** — Button（3 variant）、Modal、Toast（自动消失）、Badge、Spinner、Dropdown
5. **Layout Shell** — AppLayout = Sidebar frame + Topbar + MainContent slot，移动端 sidebar 变 drawer

### Phase 2: 基础设施

**目标**：API 调用、SSE 流式、路由全部 typed 可用

6. **API Client** — typed fetch wrapper，401 自动 refresh（singleton promise 防风暴），响应自动 unwrap `.data`
7. **useSSE Hook** — 14 种事件类型 typed，RAF throttle buffer，exponential backoff reconnect（max 5 次）
8. **Router** — React Router v6，lazy loading per route，auth guard（未登录→login）
9. **Global Context** — AuthContext（token/user/login/logout）、ThemeContext（light/dark/density）、SessionContext（current session/list）

### Phase 3: 核心体验（重做）

**目标**：用户第一眼接触的页面达到 Manus 级别

10. **Auth 页面** — Login（email/password + magic link + Google OAuth）、Register（+ 邀请码）、OAuth callback 处理
11. **Chat 页面** —
    - MessageList：按角色分布（user 右 / assistant 左），流式 text_delta 逐字追加
    - Composer：Enter 发送 / Shift+Enter 换行，队列 toast
    - ToolCard：折叠/展开，running/ok/error 状态 badge，持续时间
    - PermissionModal：倒计时（5min→默认拒绝），允许/拒绝按钮
    - PlanPanel：Coordinator step 进度条
12. **Content Renderer** —
    - 管线：`marked.parse()` → `DOMPurify.sanitize()` → 自定义 token handler
    - 代码块：Prism.js 语法高亮 + 一键复制 + 语言标签
    - 表格：styled，不是裸 `<table>`
    - 思考块：`[思考]` → 可折叠灰色区域
    - 工具调用：内联 ToolCard 组件
    - HTML 渲染：LLM 输出中包含 HTML 标签时直接渲染（DOMPurify 过滤后），不转义为纯文本；纯 Markdown 内容走 marked 管线（对齐 Claude/Anthropic 方向）
13. **Markdown 导出** —
    - Turndown.js 将渲染后的 HTML 反序列化为干净 Markdown
    - 自定义规则：ToolCard → code block，ThinkingBlock → blockquote
    - 导出方式：下载 .md 文件、复制到剪贴板
14. **Sidebar** —
    - 会话列表按时间分组（今天/昨天/本周/更早）
    - 搜索（debounce 300ms）
    - 新对话按钮
    - 移动端：overlay + hamburger toggle

### Phase 4: 功能页面（提取+升级）

**目标**：所有功能页面链路完整可用

15. **Sessions 页** — 完整列表 + 搜索 + 删除确认 + 导出对话（Markdown）
16. **Settings 页** — 5 个 Tab：
    - Profile：头像/昵称/邮箱/改密码
    - Providers：CRUD + 测试连接 + 预置 presets + 能力检测 badge
    - MCP：Server 列表 / 添加 / 删除
    - IM：渠道配置 / 配对码生成 / 绑定状态
    - Preferences：主题 / 密度 / 语言
17. **Skills Market** — 多源搜索（local+GitHub+marketplace）+ rapidfuzz 模糊匹配 + 安装/卸载 + README 面板 + 来源 Badge
18. **Plugin Builder** — CC-style 单输入框 + AI 对话流程 + 保存/导出（无 YAML 编辑器）
19. **Usage 页** — 7 天 token 趋势 + Provider 成本饼图 + Cache hit rate 卡片 + 节省金额
20. **Observability 页** — Harness 事件列表 + 每 run 的 turn/tool 统计 + 信号指标

### Phase 5: Admin（提取+升级）

**目标**：Admin 面板从半成品到功能完整

21. **Admin Layout** — 深色侧边栏 rail + 内容区
22. **用户管理** — 列表 / 角色切换 / 禁用 / 最后 admin 保护 + 邀请码 CRUD
23. **系统统计** — 24h runs / 7d 成本 / 活跃用户 / Cache 节省
24. **审计日志** — 按 action/user/时间筛选 + CSV 导出（10k cap）
25. **Provider/MCP/Guardrails** — Admin 级管理面板

### Phase 6: 商业级打磨

**目标**：达到 Manus 级产品质量

26. **移动端全面适配** — 每个页面在 390×844 下验证
27. **Dark Mode** — token-based 主题切换，`prefers-color-scheme` 跟随
28. **无障碍** — ARIA labels / keyboard navigation / focus trap (Modal) / skip-nav
29. **性能** — React.lazy per route / React.memo 热组件 / 图片 lazy load
30. **Error Boundary** — 页面级降级 UI + 网络离线提示 + loading skeleton

---

## 5. 内容渲染架构

```
LLM 输出 (Markdown/text)
    │
    ▼
ContentRenderer 组件
    │  marked.parse() — Markdown → raw HTML
    ▼
DOMPurify.sanitize() — 安全过滤
    │
    ▼  自定义 token handler
    ├── 代码块 → <CodeBlock /> (Prism.js 高亮 + 复制按钮 + 语言标签)
    ├── 表格 → <StyledTable /> (边框 + 斑马纹 + 水平滚动)
    ├── 工具调用 → <ToolCard /> (可折叠, running/ok/error badge)
    ├── 思考块 → <ThinkingBlock /> (可折叠灰色区)
    └── 图片 → <ImagePreview /> (lazy load + lightbox)
    │
    ▼
渲染的 HTML (浏览器展示)
    │
    ▼  exportAsMarkdown()
    │  Turndown.js — HTML → clean Markdown
    │  自定义规则: ToolCard → ```tool block, ThinkingBlock → > blockquote
    ▼
干净 Markdown (导出: .md 下载 / 剪贴板复制)
```

---

## 6. 与后端的对接

### 不变的部分
- 所有 REST API 端点不变（`/api/v1/*`）
- SSE 事件协议不变（14 种事件类型）
- Auth 流程不变（access_token sessionStorage + refresh_token HttpOnly cookie）
- nginx 反向代理配置更新：`/` 指向 Vite build 产物

### 新增
- Vite dev server 的代理配置（`proxy: { '/api': 'http://localhost:8000' }`）
- nginx 配置更新：静态文件从 `frontend/` → `frontend-react/dist/`

---

## 7. 迁移策略

1. 新项目建在 `frontend-react/`，不删除旧 `frontend/`
2. 开发期间 Vite dev server 跑在独立端口，proxy 到后端
3. 每个 Phase 完成后做 E2E Playwright 验证（桌面 + 移动端）
4. 所有 Phase 完成后，nginx 切到新前端，旧 `frontend/` 归档
5. Docker Compose 更新构建流程：Vite build → nginx 静态托管

---

## 8. 验收标准

- TypeScript strict，零 `any`，零编译错误
- 每个页面桌面端（≥1280px）+ 移动端（390×844）Playwright 验证
- 每个交互流程完整模拟人走一遍（不是只看截图）
- Content Renderer：Markdown 渲染 + HTML 展示 + Markdown 导出 roundtrip 无损
- Lighthouse Performance ≥ 80，Accessibility ≥ 90
- 现有功能零回归（所有后端 API 调用链路通畅）
