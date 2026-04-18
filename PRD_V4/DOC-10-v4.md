# Prism 棱镜 v2 — Frontend Foundation (DOC-10)

> **文档编号**: DOC-10
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — 前端基础架构搭建,所有页面的公共基础
> **前置依赖**: DOC-01 v4(API 路由总表 + SSE 协议), DOC-06 v4 ~ DOC-09 v4(所有后端 API 已完成), UI design spec(2026-04-07 视觉真相源)
> **Phase**: 3(前端)
> **Task 数**: 4(v4 新增 Task 10.4 视觉系统与组件库)
> **v4 变更摘要**: 基于 5 轮 review 修订,20 处精确修补(详见文末 §附录 A)。**本份文档是最大规模扩充(9KB → ~50KB)**。核心修订:前言明确三份前端文档职责分界、**useSSE hook 完整状态机**(idle/connecting/open/reconnecting/closed + 指数退避 + ticket 换取 + last_event_id 补发)、**apiClient 完整实现**(错误处理 / 重试 / 401 自动跳转 / 404 / 超时 / AbortController / TanStack Query 集成)、视觉系统(从 UI design spec 移植 tokens 到 Tailwind)、基础组件库(ChatMessage / ToolCard / HarnessNotification / **PermissionAskModal** / **CoordinatorPlanPanel**)、多 tab 限制提示。ADR 编号从 ADR-090 接续至 ADR-095。
> **审计关注点**:
> - **前端三份文档职责分界**:UI design spec(视觉真相源) / DOC-10 v4(技术基建) / DOC-11 v4(业务功能)。冲突时以 UI design spec 的视觉规范为准(像素/色值/字体/间距),技术实现遵循 DOC-10/11
> - **SSE 事件需处理多种类型**:前端 SSE 客户端必须识别并处理 `text_delta / tool_use_delta / message_complete / harness_event / permission_ask / coordinator_plan_update / run_crashed` 事件,将 Harness 治理动态实时展示。不能 silently ignore

---

## 前言:三份前端文档的职责分界(v4 新增)

前端实现涉及三份文档,各自职责明确:

| 文档 | 职责 | 冲突时的优先级 |
|---|---|---|
| **UI design spec(2026-04-07)** | **视觉真相源** — 色值、字体、间距、阴影、动效曲线、响应式断点、双态布局(桌面/移动) | 视觉规范冲突时以此为准 |
| **DOC-10 v4(本份)** | **技术基建** — Next.js 搭建、SSE 客户端、API 客户端、错误上报、基础组件库、设计 tokens 映射到 Tailwind | 技术实现冲突时以此为准 |
| **DOC-11 v4** | **业务功能** — Chat 界面、Session 管理、IM 绑定 UX、用量仪表盘、Skills Store、Admin Obs 面板 | 业务逻辑以此为准 |

冲突决议规则:
1. 视觉规范(看起来应该是什么样) → UI design spec
2. 技术基础设施(SSE / API / 组件库 / 错误处理) → DOC-10
3. 具体业务页面交互逻辑 → DOC-11
4. 如果三者冲突,向用户 escalate,不自行决定

---

## 目录

1. [Task 10.1: Next.js 项目搭建与设计系统](#task-101-nextjs-项目搭建与设计系统)
2. [Task 10.2: SSE 客户端封装(v4:完整状态机 + ticket + last_event_id)](#task-102-sse-客户端封装)
3. [Task 10.3: API 客户端与认证状态管理(v4:完整错误处理 + 重试)](#task-103-api-客户端与认证状态管理)
4. [Task 10.4: 视觉系统与基础组件库(v4 新增)](#task-104-视觉系统与基础组件库)

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

## Task 10.2: SSE 客户端封装(v4:完整状态机 + ticket + last_event_id + 新事件类型)

### Part A — 设计与解释

#### 问题陈述

前端需要通过 SSE 接收 Agent 执行的实时事件。DOC-01 v4 §7 定义了事件类型,v4 新增 `permission_ask / coordinator_plan_update / run_crashed / message_complete / tool_use_delta` 等事件。**v4 重大修订**:SSE 认证从 URL query JWT 改为 ticket 换取(DOC-06 v4 ADR-051),断线重连带 `last_event_id` 请求补发历史(DOC-07 v4 SSE Manager)。

#### 设计决策(ADR)

- **ADR-090(useSSE hook 状态机)**:SSE 连接状态必须用显式状态机管理,**5 种状态**:
  - `idle` — 初始状态,未连接
  - `connecting` — 正在换取 ticket + 建立 EventSource
  - `open` — EventSource open,收 events
  - `reconnecting` — 断线,指数退避等待重连
  - `closed` — 被用户或 unmount 关闭

  来源:Batch 4 §B4-4。

- **ADR-091(SSE ticket 换取流程)**:前端发起 SSE 连接时:
  1. `POST /auth/sse-ticket {session_id}` → 获得 `{ticket, expires_at}`
  2. `new EventSource("/sessions/{id}/stream?ticket=X&last_event_id=Y")`
  3. EventSource open / error 触发状态机转换

  来源:Batch 1 v2 §R4, DOC-06 v4 ADR-051。

- **ADR-092(断线重连指数退避 + lastEventId 补发)**:重连延迟 `min(1000 * 2^attempts, 30000) ms`,最多 30s。每次重连带当前 lastEventId 请求 Backend 补发 Redis Stream 中该 id 之后的事件。来源:Batch 1 v2 §R4, Batch 4 §B4-4。

#### SSE 事件处理矩阵(v4 扩展)

| 事件 | 前端行为 |
|------|---------|
| `text_delta` | 追加到对话区的 assistant 消息(streaming 打字效果) |
| `tool_use_delta`(v4) | 工具入参 JSON 流式展示 |
| `message_complete`(v4) | 把 streaming 消息替换为最终完整版本 |
| `tool_start` | 显示工具调用卡片(折叠状态,显示工具名和参数) |
| `tool_end` | 更新工具卡片状态(完成/失败 + 耗时 + 结果预览) |
| **`permission_ask`(v4)** | **弹 PermissionAskModal,用户点"允许/拒绝"调 `POST /sessions/{id}/permission-answer`** |
| **`coordinator_plan_update`(v4)** | **CoordinatorPlanPanel 组件更新步骤进度** |
| `plan_step` | 显示步骤列表(Coordinator 模式) |
| `step_start` / `step_end` | 步骤状态更新 |
| `harness_event` ⚡ | 根据 subtype 显示 Harness 治理通知(toast / inline badge) |
| `run_complete` | 显示完成状态 + token 用量 + cache 节省 |
| `run_error` | 显示错误信息 |
| **`run_crashed`(v4)** | **弹"Run 异常中断"提示 + 显示 `POST /runs/{id}/resume` 恢复按钮** |
| `queue_update` | 更新排队状态提示 |
| `heartbeat` | 忽略(仅保活) |
| `session_title` | 更新侧边栏会话标题 |

#### harness_event subtype 展示策略(不变)

| 子类型 | 展示方式 |
|--------|---------|
| `guardrail_trigger` | Toast 警告 + 详情面板高亮 |
| `permission_deny` | Toast 通知 |
| `loop_detected` | Toast 提示 + 循环计数 |
| `compaction` | 静默通知(底部状态栏) |
| `circuit_break` | Toast 错误 + 重试建议 |
| `feedback_alert` | Toast 警告 + 链接到仪表盘 |
| `middleware_action` | 静默通知(调试面板可见) |

#### 验收标准(v4 扩展)

- SSE 客户端通过 `POST /auth/sse-ticket` 换取 ticket,然后 `new EventSource(?ticket=X&last_event_id=Y)`
- **所有事件类型都有对应的处理逻辑(不 silently ignore)** — text_delta / tool_use_delta / message_complete / tool_start / tool_end / permission_ask / coordinator_plan_update / harness_event / run_complete / run_error / run_crashed / queue_update / heartbeat / session_title
- `harness_event` 按 subtype 差异化展示
- **断线自动重连(指数退避 1s/2s/4s/.../30s)**
- **重连时带 lastEventId 请求 Backend 补发 Redis Stream 中该 id 之后的事件**
- **`permission_ask` 事件弹 PermissionAskModal 组件**,用户点击后 POST 到 Backend
- **`run_crashed` 事件显示恢复提示 + `POST /runs/{id}/resume` 按钮**
- Token 过期时关闭连接并提示重新登录
- **多 tab 限制**:Backend 返回 429 时前端展示"本会话已打开多个窗口,请关闭其他标签"

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

### 2. lib/sse-client.ts(v4:ticket + last_event_id)

参考 hooks/use-sse.ts 下方的完整实现。lib/sse-client.ts 是更底层的类,提供 `SSEClient` 类,useSSE hook 封装它。

### 3. hooks/use-sse.ts(v4:完整状态机)

```typescript
/**
 * useSSE - SSE 连接 React hook(v4 ADR-090/091/092)
 * 支持:ticket 换取 / 自动重连 / last_event_id 补发 / 状态机 / 事件分发
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { apiClient } from '@/lib/api-client'

type SSEState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

interface UseSSEOptions {
  sessionId: string
  onTextDelta: (text: string, messageId: string) => void
  onToolUseDelta: (toolUseId: string, partialJson: string) => void
  onMessageComplete: (message: any) => void
  onToolStart: (data: any) => void
  onToolEnd: (data: any) => void
  onHarnessEvent: (event: any) => void
  onPermissionAsk: (req: any) => void
  onCoordinatorPlanUpdate: (plan: any) => void
  onRunComplete: (summary: any) => void
  onRunError: (error: any) => void
  onRunCrashed: (crash: any) => void
  onQueueUpdate?: (data: any) => void
  onSessionTitle?: (data: any) => void
}

export function useSSE(options: UseSSEOptions) {
  const [state, setState] = useState<SSEState>('idle')
  const [multiTabError, setMultiTabError] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isClosedRef = useRef(false)

  const connect = useCallback(async () => {
    if (isClosedRef.current) return
    setState('connecting')

    try {
      // 1. 换取 ticket(v4 ADR-091)
      const ticketResp = await apiClient.post('/auth/sse-ticket', {
        session_id: options.sessionId,
      })
      const { ticket } = ticketResp.data

      // 2. 建立 EventSource
      const url = new URL(
        `/api/v1/sessions/${options.sessionId}/stream`,
        window.location.origin,
      )
      url.searchParams.set('ticket', ticket)
      if (lastEventIdRef.current) {
        url.searchParams.set('last_event_id', lastEventIdRef.current)
      }

      const es = new EventSource(url.toString())
      esRef.current = es

      es.onopen = () => {
        setState('open')
        reconnectAttempts.current = 0
        setMultiTabError(false)
      }

      const bind = (eventName: string, handler: (data: any) => void) => {
        es.addEventListener(eventName, (e: MessageEvent) => {
          lastEventIdRef.current = e.lastEventId
          try {
            handler(JSON.parse(e.data))
          } catch (err) {
            console.error(`SSE ${eventName} parse failed`, err)
          }
        })
      }

      bind('text_delta', (d) => options.onTextDelta(d.text, d.message_id))
      bind('tool_use_delta', (d) => options.onToolUseDelta(d.tool_use_id, d.partial_json))
      bind('message_complete', options.onMessageComplete)
      bind('tool_start', options.onToolStart)
      bind('tool_end', options.onToolEnd)
      bind('permission_ask', options.onPermissionAsk)
      bind('coordinator_plan_update', options.onCoordinatorPlanUpdate)
      bind('harness_event', options.onHarnessEvent)
      bind('run_complete', options.onRunComplete)
      bind('run_error', options.onRunError)
      bind('run_crashed', options.onRunCrashed)
      if (options.onQueueUpdate) bind('queue_update', options.onQueueUpdate)
      if (options.onSessionTitle) bind('session_title', options.onSessionTitle)

      es.onerror = (e) => {
        if (isClosedRef.current) return
        setState('reconnecting')
        es.close()
        esRef.current = null

        // v4 ADR-092:指数退避重连(1s / 2s / 4s / ... / 30s)
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
        reconnectAttempts.current++

        reconnectTimerRef.current = setTimeout(() => connect(), delay)
      }

    } catch (err: any) {
      // 多 tab 限制 429
      if (err?.response?.status === 429) {
        setMultiTabError(true)
        setState('closed')
        return
      }
      // 401 ticket 失败 → 上层 apiClient 会自动跳登录
      console.error('SSE connect failed:', err)
      setState('closed')
    }
  }, [options])

  useEffect(() => {
    isClosedRef.current = false
    connect()
    return () => {
      isClosedRef.current = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      esRef.current?.close()
      setState('closed')
    }
  }, [connect])

  return {
    state,
    reconnect: connect,
    multiTabError,
    lastEventId: lastEventIdRef.current,
  }
}
```

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

## Task 10.3: API 客户端与认证状态管理(v4:完整实现 + 重试 + 错误上报)

### Part A — 设计与解释

#### 问题陈述

前端需要统一的 API 客户端(fetch 封装 + JWT 自动续期)和认证状态管理(登录/注册/登出/token 存储)。v4 扩充完整的错误处理、重试策略、取消支持、TanStack Query 集成、前端错误上报。

#### 设计决策(ADR)

- **ADR-093(apiClient 错误分类)**:HTTP 错误按 status 分类处理:
  - 401 → 尝试 `/auth/refresh` 续期;再 401 → 清 token + 跳转 /login
  - 403 → 弹 Toast("权限不足")
  - 404 → 抛 `NotFoundError`,由 React Query 交给 ErrorBoundary 渲染 404 UI
  - 409 → 抛 `ConflictError`,Component 自行处理(如多 tab 限制)
  - 429 → 尝试 1 次重试(带 Retry-After 头),失败抛 `RateLimitError`
  - 5xx → 指数退避重试最多 3 次(POST/PUT/DELETE 默认不重试,除非 method 显式 idempotent=true)
  - 网络错误 → 重试 3 次,最终失败抛 `NetworkError`

- **ADR-094(AbortController 支持)**:所有 apiClient 方法接受 `signal: AbortSignal`,支持组件 unmount 时取消请求。与 TanStack Query 的 `signal` 选项对齐。

- **ADR-095(前端错误上报)**:所有未处理的 Error(ErrorBoundary / window.onerror / unhandledrejection)通过 `POST /api/v1/frontend-errors`(DOC-12 v4 Task 12.7)上报:`{error_id, message, stack, url, user_agent, viewport, user_id, session_id, severity}`。

#### 验收标准(v4 扩展)

- API 客户端自动附加 Authorization header
- access_token 过期时自动通过 /auth/refresh 续期
- 续期失败时清 token + 跳转登录页
- 登录/注册页面可用
- 登出后清除所有状态
- **v4:5xx 错误重试(指数退避,最多 3 次,GET/HEAD 默认;POST 需 idempotent=true 才重试)**
- **v4:429 支持 Retry-After 重试一次**
- **v4:AbortController 集成,组件 unmount 自动取消请求**
- **v4:TanStack Query 集成,queryFn 自动接收 signal**
- **v4:未处理错误通过 `POST /api/v1/frontend-errors` 上报到 Backend**

---

### Part B — Claude Code 执行 Prompt

> **v4 Observability 采集要求**:
> - 所有未捕获 Error 通过 `POST /frontend-errors` 上报
> - Web Vitals(LCP/INP/CLS)通过 `web-vitals` 库采集后上报 Prometheus `prism_web_vitals_histogram{metric,route}`
> - 首 token 延迟:在 SSE 收到第一个 text_delta 时 `performance.now() - userSubmitTime` 上报

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 API 客户端和认证管理。v4 要求完整的错误处理/重试/取消/上报。

## 要创建的文件

```
frontend/src/
├── lib/
│   ├── api-client.ts              # fetch 封装 + 自动续期 + 重试 + AbortController
│   ├── errors.ts                  # 自定义错误类(NotFoundError / ConflictError / RateLimitError / NetworkError)
│   ├── error-reporter.ts          # 错误上报
│   └── web-vitals.ts              # Web Vitals 采集上报
├── stores/
│   └── auth-store.ts              # 认证状态(Zustand)
├── components/
│   └── ErrorBoundary.tsx          # 全局 ErrorBoundary
└── app/
    ├── login/page.tsx
    └── register/page.tsx
```

## 实现规范

### 1. lib/errors.ts

```typescript
export class ApiError extends Error {
  constructor(public status: number, public payload: any, message?: string) {
    super(message || `HTTP ${status}`)
  }
}
export class NotFoundError extends ApiError {}
export class ConflictError extends ApiError {}
export class RateLimitError extends ApiError {}
export class NetworkError extends Error {}
export class UnauthorizedError extends ApiError {}
```

### 2. lib/api-client.ts(v4 完整实现)

```typescript
import { useAuthStore } from '@/stores/auth-store'
import {
  ApiError, NotFoundError, ConflictError, RateLimitError,
  NetworkError, UnauthorizedError,
} from './errors'
import { reportError } from './error-reporter'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1'
const DEFAULT_TIMEOUT_MS = 30000
const MAX_5XX_RETRIES = 3

export interface RequestOptions {
  signal?: AbortSignal
  timeout?: number
  idempotent?: boolean    // POST/PUT/DELETE 需显式标记才重试
  headers?: Record<string, string>
  body?: any
  method?: string
}

async function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms))
}

let refreshingPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (refreshingPromise) return refreshingPromise
  refreshingPromise = (async () => {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!resp.ok) {
      useAuthStore.getState().clear()
      if (typeof window !== 'undefined') window.location.href = '/login'
      throw new UnauthorizedError(401, {})
    }
    const data = await resp.json()
    useAuthStore.getState().setAccessToken(data.data.access_token)
    return data.data.access_token as string
  })()
  try {
    return await refreshingPromise
  } finally {
    refreshingPromise = null
  }
}

async function doFetch(path: string, opt: RequestOptions = {}, attempt = 0): Promise<any> {
  const method = (opt.method || 'GET').toUpperCase()
  const token = useAuthStore.getState().accessToken
  const controller = new AbortController()
  const timeout = opt.timeout ?? DEFAULT_TIMEOUT_MS

  // 合并外部 signal
  opt.signal?.addEventListener('abort', () => controller.abort())
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method,
      signal: controller.signal,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(opt.headers || {}),
      },
      body: opt.body ? JSON.stringify(opt.body) : undefined,
    })

    // 401:尝试续期一次
    if (resp.status === 401 && attempt === 0) {
      await refreshAccessToken()
      return doFetch(path, opt, attempt + 1)
    }
    if (resp.status === 401) {
      throw new UnauthorizedError(401, await resp.json().catch(() => ({})))
    }

    // 429 带 Retry-After 重试一次
    if (resp.status === 429 && attempt === 0) {
      const retryAfter = parseInt(resp.headers.get('Retry-After') || '1', 10)
      await sleep(retryAfter * 1000)
      return doFetch(path, opt, attempt + 1)
    }
    if (resp.status === 429) {
      throw new RateLimitError(429, await resp.json().catch(() => ({})))
    }

    // 404
    if (resp.status === 404) {
      throw new NotFoundError(404, await resp.json().catch(() => ({})))
    }

    // 409
    if (resp.status === 409) {
      throw new ConflictError(409, await resp.json().catch(() => ({})))
    }

    // 5xx:幂等方法重试
    if (resp.status >= 500 && resp.status < 600) {
      const canRetry = (method === 'GET' || method === 'HEAD' || opt.idempotent)
      if (canRetry && attempt < MAX_5XX_RETRIES) {
        const delay = Math.min(500 * 2 ** attempt, 8000)
        await sleep(delay)
        return doFetch(path, opt, attempt + 1)
      }
      throw new ApiError(resp.status, await resp.json().catch(() => ({})))
    }

    // 其他非 2xx
    if (!resp.ok) {
      throw new ApiError(resp.status, await resp.json().catch(() => ({})))
    }

    // 成功
    return resp.json()
  } catch (err: any) {
    if (err.name === 'AbortError') {
      // 用户取消或超时
      throw err
    }
    // 网络错误
    if (!(err instanceof ApiError) && err instanceof Error && err.message?.includes('fetch')) {
      if (attempt < MAX_5XX_RETRIES && (method === 'GET' || opt.idempotent)) {
        const delay = Math.min(500 * 2 ** attempt, 8000)
        await sleep(delay)
        return doFetch(path, opt, attempt + 1)
      }
      throw new NetworkError(err.message)
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export const apiClient = {
  get: (path: string, opt?: RequestOptions) => doFetch(path, { ...opt, method: 'GET' }),
  post: (path: string, body?: any, opt?: RequestOptions) => doFetch(path, { ...opt, method: 'POST', body }),
  put: (path: string, body?: any, opt?: RequestOptions) => doFetch(path, { ...opt, method: 'PUT', body, idempotent: true }),
  patch: (path: string, body?: any, opt?: RequestOptions) => doFetch(path, { ...opt, method: 'PATCH', body }),
  delete: (path: string, opt?: RequestOptions) => doFetch(path, { ...opt, method: 'DELETE', idempotent: true }),
}
```

### 3. lib/error-reporter.ts(v4)

```typescript
import { useAuthStore } from '@/stores/auth-store'

export async function reportError(error: Error, context: Record<string, any> = {}) {
  try {
    const viewport = `${window.innerWidth}x${window.innerHeight}`
    await fetch('/api/v1/frontend-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: error.message,
        stack: error.stack,
        name: error.name,
        url: window.location.href,
        user_agent: navigator.userAgent,
        viewport,
        user_id: useAuthStore.getState().user?.id,
        context,
        severity: (error as any).severity || 'error',
        timestamp: new Date().toISOString(),
      }),
    })
  } catch {
    // 错误上报本身不能再引发错误
  }
}

// 全局监听
if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => {
    reportError(e.error || new Error(e.message), { source: 'window.onerror' })
  })
  window.addEventListener('unhandledrejection', (e) => {
    const err = e.reason instanceof Error ? e.reason : new Error(String(e.reason))
    reportError(err, { source: 'unhandledrejection' })
  })
}
```

### 4. components/ErrorBoundary.tsx

```tsx
'use client'
import React from 'react'
import { reportError } from '@/lib/error-reporter'

interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    reportError(error, { componentStack: info.componentStack })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 text-center">
          <h2 className="text-xl font-semibold">出错了</h2>
          <p className="text-sm text-zinc-500 mt-2">{this.state.error?.message}</p>
          <button onClick={() => this.setState({ hasError: false, error: null })}
                  className="mt-4 px-4 py-2 bg-amber-600 text-white rounded">
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
```

### 5. TanStack Query 集成

```typescript
// providers/react-query.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      queryFn: async ({ queryKey, signal }) => {
        const [path] = queryKey as [string]
        return apiClient.get(path, { signal })
      },
      retry: false,           // 重试由 apiClient 控制,React Query 层不重试
      staleTime: 30_000,
    },
  },
})
```

## 验证步骤

```bash
npx tsc --noEmit

# 单元测试
npm run test lib/api-client.test.ts
# 重点测试:
# - 401 自动续期 → 续期成功重试原请求
# - 429 带 Retry-After 重试一次
# - 5xx 指数退避重试 3 次
# - POST 默认不重试(除非 idempotent=true)
# - 网络错误 GET 重试,其他不重试
# - AbortController 生效

# Playwright E2E(桌面 1280x800 + 移动 375x812)
npx playwright test auth.spec.ts
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md:记录 ADR-093/094/095
3. `git add -A && git commit -m "feat(v4): api-client with 401/429/5xx handling + error boundary + frontend errors reporter"`
```

---

## Task 10.4: 视觉系统与基础组件库(v4 新增)

### Part A — 设计与解释

#### 问题陈述

UI design spec(2026-04-07)定义了 Prism 的视觉真相源。本 Task 把 design tokens 移植到 Tailwind 配置,并实现跨页面复用的基础组件(ChatMessage / ToolCard / HarnessNotification / PermissionAskModal / CoordinatorPlanPanel 等)。DOC-11 v4 的业务页面直接使用这些组件。

#### 验收标准

- Tailwind 配置含完整 design tokens(colors / typography / spacing / shadows / radii / transitions)
- 基础组件库可用:
  - `<ChatMessage role="user|assistant" content={...} />`
  - `<ToolCard toolName toolInput toolOutput status />`
  - `<HarnessNotification subtype detail />`
  - `<PermissionAskModal request onDecision />`
  - `<CoordinatorPlanPanel plan currentStep />`
  - `<MultiTabErrorBanner />`
- 桌面 + 移动双视口 Playwright 截图基线通过
- Storybook(可选)展示每个组件的所有状态

### Part B — 实现规范

#### 1. tailwind.config.ts design tokens

从 UI design spec 移植(色值/字体/间距/阴影参考该文档),示例结构:
```typescript
export default {
  theme: {
    extend: {
      colors: {
        background: '#FAFAF8',
        foreground: '#1A1A1A',
        accent: { DEFAULT: '#D97706', hover: '#B45309' },
        muted: { DEFAULT: '#F4F4F0', foreground: '#6B6B6B' },
        border: '#E5E5E0',
        // harness 事件色
        warning: '#F59E0B',
        danger: '#DC2626',
        success: '#10B981',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      spacing: { /* 8px 基准 */ },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06)',
      },
      // 其他见 UI design spec
    },
  },
}
```

#### 2. components/chat/ChatMessage.tsx

渲染 `role=user/assistant` 消息,支持 text 块 + tool_use 块 + tool_result 块的嵌套展示。Markdown 用 `react-markdown` + `remark-gfm` + 语法高亮。

#### 3. components/chat/ToolCard.tsx

工具调用卡片,三态:`running / completed / error`。折叠展示工具名 + 参数 preview;展开显示完整 input + output + duration_ms。

#### 4. components/harness/HarnessNotification.tsx

按 subtype 渲染不同样式:
- `guardrail_trigger` / `permission_deny`:`bg-danger/10 border-danger` 红色警示条
- `loop_detected` / `circuit_break`:`bg-warning/10 border-warning` 黄色警告
- `compaction`:`text-muted-foreground` 灰色静默行
- `feedback_alert`:Toast 右下角,3s 后消失

#### 5. components/harness/PermissionAskModal.tsx(v4 核心)

```tsx
interface PermissionAskRequest {
  request_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  reason: string
  timeout_at: string
}

export function PermissionAskModal({
  request,
  onDecision,
}: {
  request: PermissionAskRequest | null
  onDecision: (requestId: string, decision: 'allow' | 'deny') => Promise<void>
}) {
  if (!request) return null
  const remaining = Math.max(0, new Date(request.timeout_at).getTime() - Date.now())
  return (
    <Dialog open>
      <DialogContent>
        <DialogHeader>Agent 需要你的确认</DialogHeader>
        <div>
          <p>工具: <code>{request.tool_name}</code></p>
          <p>原因: {request.reason}</p>
          <pre className="bg-muted p-2 rounded text-xs max-h-48 overflow-auto">
            {JSON.stringify(request.tool_input, null, 2)}
          </pre>
          <p className="text-xs text-muted-foreground mt-2">
            {Math.floor(remaining / 1000)} 秒后自动拒绝
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onDecision(request.request_id, 'deny')}>
            拒绝
          </Button>
          <Button onClick={() => onDecision(request.request_id, 'allow')}>
            允许
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

#### 6. components/harness/CoordinatorPlanPanel.tsx(v4 核心)

展示 Coordinator 的多步骤计划进度:steps 列表(description / agent_type / status icon / duration)+ 当前 step 高亮 + 整体进度条。订阅 `coordinator_plan_update` SSE 事件实时更新。

#### 7. components/system/MultiTabErrorBanner.tsx

SSE 429 时展示,提示"此会话已在其他窗口打开(最多 3 个),请关闭其他标签页"。

## 验证步骤

```bash
npx tsc --noEmit

# Playwright 双视口截图基线
npx playwright test --grep "visual regression" --project=chromium-desktop
npx playwright test --grep "visual regression" --project=chromium-mobile
```

## 完成后

1. 更新 PROGRESS.md:Task 10.4 完成
2. `git add -A && git commit -m "feat(v4): design tokens + base component library (chat/tool/harness/permission-ask/coordinator)"`

---

## 附录 A: v4 修订清单

本次修订共 20 处精确修补,对应 Batch 1-5 review + UI design spec:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,Task 数 3 → 4,v4 摘要段 | 全局 |
| 2 | **DOC 开头新增前言** | 明确三份前端文档的关系:UI design spec=视觉真相源 / DOC-10=技术基建 / DOC-11=业务功能 + 冲突决议规则 | Batch 4 §B4-I, Master M6 |
| 3 | Task 10.1 Part A | 保留,加 v4 UI design spec 作为视觉真相源的引用 | — |
| 4 | **Task 10.2 重大扩充** | 从"几行简述" → 完整 useSSE hook 实现规范 | Batch 4 §B4-1 |
| 5 | Task 10.2 useSSE 状态机 | ADR-090:`idle → connecting → open → reconnecting → closed`(含重连指数退避) | Batch 4 §B4-4 |
| 6 | Task 10.2 ticket 换取流程 | ADR-091:`POST /auth/sse-ticket` → `new EventSource(?ticket=X&last_event_id=Y)` | Batch 1 v2 §R4 |
| 7 | Task 10.2 事件处理 | 所有事件类型(含 v4 新增 permission_ask / coordinator_plan_update / run_crashed / message_complete / tool_use_delta)对应 handler | Batch 4 §B4-4 |
| 8 | Task 10.2 断线重连补发 | ADR-092:EventSource `lastEventId` + 重连时带 last_event_id 从 Backend 补发 | Batch 1 v2 §R4 |
| 9 | **Task 10.3 重大扩充** | 从"几行简述" → 完整 apiClient 实现(含错误处理 / 重试 / 401 自动跳转 / 404 / 超时 / AbortController) | Batch 4 §B4-1 |
| 10 | Task 10.3 apiClient 完整代码 | ADR-093:401→refresh→401 则清 token 跳 login;429 Retry-After 重试一次;5xx 指数退避 3 次;POST 非幂等不重试(idempotent=true 才重试) | 同上 |
| 11 | Task 10.3 AbortController + TanStack Query | ADR-094:所有方法接受 `signal: AbortSignal`,与 TanStack Query queryFn signal 对齐 | 同上 |
| 12 | Task 10.3 错误上报 | ADR-095:ErrorBoundary + window.onerror + unhandledrejection → `POST /api/v1/frontend-errors`(DOC-12 v4 Task 12.7) | Batch 5 §B5-I |
| 13 | **Task 10.4 新增:视觉系统 + 基础组件库** | Tailwind design tokens 从 UI design spec 移植 + `<ChatMessage>` / `<ToolCard>` / `<HarnessNotification>` 组件 | UI design spec |
| 14 | Task 10.4 permission_ask 弹窗 | `<PermissionAskModal>` 组件 + 订阅 SSE `permission_ask` 事件 + `POST /sessions/{id}/permission-answer` | Batch 3 B3-1, Batch 2 §A3-7 |
| 15 | Task 10.4 coordinator plan 可视化 | `<CoordinatorPlanPanel>` 组件 + 订阅 `coordinator_plan_update` 事件 | Batch 3 §A7-7 |
| 16 | Task 10.4 多 tab 限制 | `<MultiTabErrorBanner>` SSE 429 时提示 | Batch 3 §B3-III |
| 17 | 所有 Task Part B 开头 | v4 Observability:前端错误上报 + Web Vitals 上报 | Batch 5 §B5-I |
| 18 | ADR 编号 ADR-090~095 | 全局 | 全局 |
| 19 | 交叉引用 v3 → v4 | 全局 | 全局 |
| 20 | 附录 A + 文末 | 修订清单 + 下一步 DOC-11 v4 | SOP |

---

> **文档维护说明(v4)**:本文档的 4 个 Task 完成后,Prism v2 将拥有完整的前端基础架构:Next.js + Tailwind + shadcn/ui + TanStack Query + Zustand + **完整 useSSE hook(5 状态机 + ticket 换取 + 指数退避重连 + last_event_id 补发)** + **完整 apiClient(401/404/409/429/5xx 错误处理 + 重试 + AbortController + 超时)** + **ErrorBoundary + 前端错误上报** + **视觉系统(从 UI design spec 移植 tokens)** + **基础组件库**(ChatMessage / ToolCard / HarnessNotification / **PermissionAskModal** / **CoordinatorPlanPanel** / MultiTabErrorBanner)。这是 DOC-11 v4(Frontend Features)的基础。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-11 v4 Frontend Features

---

> **文档维护说明**：本文档的 3 个 Task 完成后，前端将拥有可运行的基础架构：Next.js + 设计系统 + SSE 客户端（含 harness_event 全 8 种 subtype 处理）+ API 客户端（自动 JWT 续期）+ 认证页面。这是 DOC-11（Frontend Features）的基础。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-11 Frontend Features
