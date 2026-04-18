# Prism 棱镜 v2 — Frontend Foundation (DOC-10)

> **文档编号**: DOC-10  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 前端基础架构搭建，所有页面的公共基础  
> **前置依赖**: DOC-01 v3（API 路由总表 + SSE 协议）, DOC-06-09（所有后端 API 已完成）  
> **Phase**: 3（前端）  
> **Task 数**: 3  
> **审计关注点**:  
> - **SSE 事件需处理 `harness_event` 类型**：前端 SSE 客户端必须识别并处理 `harness_event` 事件，将 Harness 治理动态（护栏拦截、循环检测、Compaction 触发等）实时展示给用户。不能 silently ignore 这个事件类型

---

## 目录

1. [Task 10.1: Next.js 项目搭建与设计系统](#task-101-nextjs-项目搭建与设计系统)
2. [Task 10.2: SSE 客户端封装（含 harness_event 处理）](#task-102-sse-客户端封装)
3. [Task 10.3: API 客户端与认证状态管理](#task-103-api-客户端与认证状态管理)

---

## Task 10.1: Next.js 项目搭建与设计系统

### Part A — 设计与解释

#### 问题陈述

Prism v2 前端从零搭建，不 fork 任何现有项目。视觉风格对标 Claude.ai 网页端：衬线标题字体、深灰/暖白配色、大量留白、简洁对话区。源码体积目标 < 10MB，构建产物 < 150MB。

#### 技术栈

- Next.js 14+（App Router）
- TypeScript strict 模式
- Tailwind CSS
- shadcn/ui 组件库
- TanStack React Query v5（服务端状态）
- Zustand（少量客户端状态）

#### 验收标准

- `npm run dev` 正常启动
- `npx tsc --noEmit` 零错误
- 设计 token（颜色、字体、间距）已定义
- Layout 组件（侧边栏 + 主内容区）已实现
- 移动端响应式（375px 断点）

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在从零搭建 Prism v2 的前端。所有后端 API 已完成（DOC-06 到 DOC-09）。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design
- uiuxpromax

## 前置条件

后端 API 全部可用（可通过 curl 验证）

## 实现要点

1. `create-next-app` 干净起步，TypeScript strict
2. 安装 shadcn/ui + Tailwind CSS + TanStack React Query + Zustand
3. 定义设计 token：
   - 配色：暖白背景 `#FAFAF8`、深灰文字 `#1A1A1A`、强调色 `#D97706`（琥珀）
   - 字体：标题衬线体（Noto Serif SC / Georgia 回退）、正文无衬线（Inter / system-ui）
   - 间距：8px 基准网格
4. 实现 Layout：侧边栏（会话列表）+ 主内容区（对话 / 设置）
5. 响应式：桌面端侧边栏固定 280px，移动端侧边栏 overlay

## 验证步骤

```bash
cd frontend
npm run dev
# 访问 http://localhost:3000，验证 Layout 渲染
npx tsc --noEmit
# 零错误
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. `git add -A && git commit -m "feat: Next.js foundation + Claude-style design system"`
```

---

## Task 10.2: SSE 客户端封装（含 harness_event 处理）

### Part A — 设计与解释

#### 问题陈述

前端需要通过 SSE 接收 Agent 执行的实时事件。DOC-01 v3 §7 定义了 11 种事件类型，其中 `harness_event` 是 Harness 治理的实时通知（护栏拦截、循环检测、Compaction 触发等），前端必须识别并展示。

#### SSE 事件处理矩阵

| 事件 | 前端行为 |
|------|---------|
| `text_delta` | 追加到对话区的 assistant 消息（streaming 打字效果） |
| `tool_start` | 显示工具调用卡片（折叠状态，显示工具名和参数） |
| `tool_end` | 更新工具卡片状态（完成/失败 + 耗时 + 结果预览） |
| `plan_step` | 显示步骤列表（Coordinator 模式） |
| `step_start` | 步骤状态更新为"执行中" |
| `step_end` | 步骤状态更新为"完成/失败" |
| `harness_event` ⚡ | 根据 subtype 显示 Harness 治理通知（toast / inline badge） |
| `run_complete` | 显示完成状态 + token 用量 |
| `run_error` | 显示错误信息 |
| `queue_update` | 更新排队状态提示 |
| `heartbeat` | 忽略（仅保活） |
| `session_title` | 更新侧边栏会话标题 |

#### harness_event subtype 展示策略

| 子类型 | 展示方式 |
|--------|---------|
| `guardrail_trigger` | Toast 警告 + 详情面板高亮 |
| `permission_deny` | Toast 通知 |
| `permission_ask` | 弹窗请求用户确认 |
| `loop_detected` | Toast 提示 + 循环计数 |
| `compaction` | 静默通知（底部状态栏） |
| `circuit_break` | Toast 错误 + 重试建议 |
| `feedback_alert` | Toast 警告 + 链接到仪表盘 |
| `middleware_action` | 静默通知（调试面板可见） |

#### 验收标准

- SSE 客户端能连接到 `/sessions/{id}/stream?token=...`
- 所有 11 种事件类型都有对应的处理逻辑（不 silently ignore）
- `harness_event` 按 subtype 差异化展示
- 断线自动重连（EventSource 原生能力 + 重连后拉取增量消息）
- Token 过期时关闭连接并提示重新登录

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 SSE 客户端封装。Task 10.1 的前端基础已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design

## 要创建的文件

```
frontend/src/
├── lib/
│   ├── sse-client.ts          # SSE 客户端封装
│   └── sse-types.ts           # SSE 事件类型定义
├── hooks/
│   └── use-sse.ts             # React Hook
└── stores/
    └── chat-store.ts          # 对话状态（Zustand）
```

## 实现规范

### 1. lib/sse-types.ts

为每种 SSE 事件定义 TypeScript 类型。不使用 any。

```typescript
// 所有事件类型的联合类型
type SSEEventType =
  | "text_delta"
  | "tool_start"
  | "tool_end"
  | "plan_step"
  | "step_start"
  | "step_end"
  | "harness_event"
  | "run_complete"
  | "run_error"
  | "queue_update"
  | "heartbeat"
  | "session_title";

// harness_event 的 subtype
type HarnessEventSubtype =
  | "guardrail_trigger"
  | "permission_deny"
  | "loop_detected"
  | "compaction"
  | "fork_start"
  | "fork_end"
  | "turn_complete"
  | "feedback_capture";

interface HarnessEventData {
  type: HarnessEventSubtype;
  detail: Record<string, unknown>;
}

// 每种事件的 data 类型...
```

### 2. lib/sse-client.ts

```typescript
/**
 * SSE 客户端封装
 *
 * 功能：
 * - 连接 /sessions/{id}/stream?token=...
 * - 按事件类型分发到不同 handler
 * - 断线自动重连
 * - Token 过期检测
 * - harness_event 按 subtype 分发
 */
```

### 3. hooks/use-sse.ts

React Hook，封装连接管理和事件分发到 Zustand store。

### 4. stores/chat-store.ts

Zustand store，管理对话状态：
- messages 列表
- 当前 streaming 文本
- 工具调用状态
- Harness 事件列表（用于展示治理通知）
- 步骤列表（Coordinator 模式）
- 队列状态
- Run 状态

## 验证步骤

```bash
npx tsc --noEmit
# 零错误

# 手动验证：启动前端 + 后端，发起一次对话，观察 SSE 事件是否被正确处理
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: SSE client with harness_event handling + chat store"`
```

---

## Task 10.3: API 客户端与认证状态管理

### Part A — 设计与解释

#### 问题陈述

前端需要统一的 API 客户端（fetch 封装 + JWT 自动续期）和认证状态管理（登录/注册/登出/token 存储）。

#### 验收标准

- API 客户端自动附加 Authorization header
- access_token 过期时自动通过 /auth/refresh 续期
- 续期失败时跳转登录页
- 登录/注册页面可用
- 登出后清除所有状态

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 API 客户端和认证管理。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers
- frontend-design

## 要创建的文件

```
frontend/src/
├── lib/
│   └── api-client.ts          # fetch 封装 + 自动续期
├── stores/
│   └── auth-store.ts          # 认证状态（Zustand）
└── app/
    ├── login/page.tsx         # 登录页
    └── register/page.tsx      # 注册页
```

## 验证步骤

```bash
npx tsc --noEmit
# Playwright E2E（桌面 1280x800 + 移动 375x812）
npx playwright test auth.spec.ts
```

## 完成后

1. 更新 PROGRESS.md
2. `git add -A && git commit -m "feat: API client with auto-refresh + auth pages"`
```

---

> **文档维护说明**：本文档的 3 个 Task 完成后，前端将拥有可运行的基础架构：Next.js + 设计系统 + SSE 客户端（含 harness_event 全 8 种 subtype 处理）+ API 客户端（自动 JWT 续期）+ 认证页面。这是 DOC-11（Frontend Features）的基础。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-11 Frontend Features
