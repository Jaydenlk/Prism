# Handoff: main → explorer

## 状态: READY_FOR_REVIEW
## 任务: 摸底 frontend/Prism.html 与 frontend/admin.html 两个入口,产出"页面结构 + 关键 DOM 区块 + 与 apiClient.js 的耦合点"双文件对照摘要

## 输入文件范围(只读,**禁止超出**)
- `frontend/Prism.html`
- `frontend/admin.html`
- `frontend/apiClient.js`(为了识别耦合点,可读)
- `frontend/styles.css`(可选,只看选择器命名风格判断 DOM 命名约定,不读完)

## 禁止触碰
- 任何 `backend/`、`executor/`、`plugins/`、`PRD_V4/` 下的文件 → 触碰即任务失败
- 任何 `.claude/memory/decisions.md` 写入 → 决策只有主 agent 写
- 任何 `.claude/plans/` 下其他 handoff 文件 → 子 agent 不互读
- 任何代码修改(包括"顺手"加注释、改格式)→ 纯只读

## 产出预期
1. 在本 handoff 文件末尾"## 子 agent 产出"小节追加内容,格式严格按 explorer.md 输出模板:
```
## 探索摘要: frontend/Prism.html + admin.html
### 结构(各文件)
- {文件名}: {一句话职责} + {≤5 行关键 DOM 区块}
### 关键发现
- {2-4 条与"对照"相关的发现,例如:共享/不共享的模块、不同的 API 调用集合}
### 潜在风险
- {如果有,例如:重复代码、不一致命名、apiClient.js 双方都用但参数风格不同}
```
2. 全部摘要 ≤ 50 行
3. 完成后将本 handoff 文件顶部状态行从 `READY_FOR_IMPL` 改为 `READY_FOR_REVIEW`(用 Edit 工具)
4. 输出精简摘要(≤80 字),不输出"我读了 XX""我打开了 XX"过程叙述

## 决策上下文(主 agent 提炼)
- DEC-001:本任务是 workflow upgrade dry-run,目的是验证派单纪律 + 范围锁定 + handoff 状态机
- 已排除方案:不调用 implementer(无代码改动);不调用 Explore 全局 agent(要测项目级链路)
- 关键观测点:你**必须**只读上面 4 个文件,触碰任何后端/PRD 文件都视为 dry-run 失败信号
- 不要使用 superpowers 系列其他 skill;不要派子子 agent;不要写 decisions.md

## 子 agent 产出

## 探索摘要: frontend/Prism.html + admin.html
### 结构(各文件)
- `Prism.html` (4240 行): 用户端 SPA(React 18 + Babel standalone CDN,单文件 JSX)。根 `<div id="root">`,`function App()` @4018 渲染 screen 状态机 (`loading|login|google_pending|app`)。app shell = `<div class="app">` → `<Sidebar>` + `<main class="main">` (含 `<Topbar>` + 6 个 page 组件 `ChatPage|SessionsPage|UsagePage|SkillsPage|PluginsPage|ObsPage|SettingsPage` + `.statusbar`) + 可选 `<PlanPanel>`。模态: `PermissionModal` / `Toasts` / `Tweaks` / `LoginScreen` / `GooglePendingScreen`。底部 E2E 钩子 `window.__e2e_mountMarkdown` 受 `?__e2e=1` 守门。
- `admin.html` (1677 行): 管理控制台 SPA(同 React/Babel 栈,单文件)。根 `<div id="root">`,`function App()` @1525 渲染 screen 状态机 (`loading|gate-nologin|gate-noadmin|app`,role=admin 才放行)。app shell = `<div class="admin-app">` → 64px 黑色 `<aside class="rail">` (12 项 `NAV` overview/tenants/users/providers/runs/guardrails/plugins/billing/audit/infra/observability/security) + `<main class="admin-main">` (含 `.admin-top` 标题栏 + `.admin-tabs` + `.admin-body` 由 `PAGES[page].r({dashData,healthData,currentUser})` 渲染)。模态 `AlertConfigModal` + `ToastContainer`。
- `apiClient.js` (695 行): 纯 vanilla JS,挂 `window.PrismAPI`。导出域: `auth/sessions/tasks/runs/admin/providers/mcp/skills/plugins/marketplaces/im/harness` + `request/requestBlob/openStream/healthDetailed/me/login/register/refresh/logout/getToken/isAuthenticated/currentUser/reportError`。token 存 sessionStorage,refresh 用 HttpOnly cookie + `prism:unauthorized` 事件总线;envelope `{data, error}` 自动解包。
### 关键发现
- 两文件**共享** `apiClient.js` 与 `styles.css`,但调用面**不重叠**:Prism.html 用 `sessions/tasks/skills/plugins/marketplaces/mcp/im/providers/auth/me`,admin.html 用 `admin.{getDashboard,listUsers,listInviteCodes,listAuditLogs,...}/healthDetailed/providers/request('GET','/im/channels')`,只有 `providers.*` 与 `me/logout/refresh/isAuthenticated` 是双方共用接触点。
- 调用风格不一致:admin.html 三处直接走 **裸 `PrismAPI.request(method, path, {json})`**(@859/867/927/956 都是 `/im/channels` 路径,绕过 `im` 域 helper),用户端全程走具名 helper。
- 两端通过 `prism:unauthorized` 事件解耦(apiClient 在 401-after-refresh-fail 时派发,Prism.html @4107 与 admin.html @1561 各自监听)。admin 未登录跳 `/Prism.html`(硬编码),Prism 端没有反向链接到 admin.html。
- React 用 UMD CDN + Babel standalone 在浏览器内编译 JSX,**没有构建步骤**;两文件均在 `<script type="text/babel">` 内全量 inline,无组件复用机制(Sidebar / Topbar / Spinner 等同名组件各自定义一份)。
### 潜在风险
- 组件**重复实现**(Spinner / EmptyState / ToastContainer / Icon 等相同语义在两文件各写一遍),后续修 bug 易漏改一边。
- admin.html 的 IM 频道页绕过 `im` 域 helper 直调 `request()`,与 Prism.html `im.listBindings/im.unbind/im.generatePairingCode` 风格分裂,后端契约变更时容易遗漏。
- 单文件 4240 + 1677 行 inline JSX + Babel standalone,首屏要在浏览器编译,生产环境性能与可维护性都不健康(无 tree-shaking、无 source map)。

## 遗留问题
无
