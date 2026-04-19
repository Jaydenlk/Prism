# Prism v2 前端集成技术手册

> **用途**：前端设计/开发团队集成参考
> **后端状态**：全栈 healthy，CloudDream LLM 真实调通，Harness middleware 真实接入
> **OpenAPI**：运行时访问 `GET /docs`（Swagger）或 `GET /openapi.json` / `GET /redoc`
> **版本**：v4 / 2026-04-19（多通道 auth + 真实 middleware + plugin_manifest_ready 事件已接通）

## 🆕 本轮关键补充

**多通道 Auth**（已实装）
| Path | Method | 说明 |
|---|---|---|
| `/auth/providers` | GET | 返回 `{email_password, email_magic, email_otp, phone_password, google}` 真实状态 |
| `/auth/email-magic/request` | POST | 邮箱 Magic Link，空值未注册也返 202（防枚举） |
| `/auth/email-magic/verify` | POST | `{challenge_id, token}` 换 access_token |
| `/auth/email-otp/request` | POST | 6 位 OTP 邮件 |
| `/auth/email-otp/verify` | POST | `{email, code}` 验码 |
| `/auth/forgot-password` | POST | 发重置链接 |
| `/auth/reset-password` | POST | `{challenge_id, token, new_password}` |
| `/auth/phone-register` | POST | 手机+密码+邀请码（暂无 SMS） |
| `/auth/phone-login` | POST | 手机+密码 |
| `/auth/google/authorize` | GET | 302 跳 Google consent（未配置返 503） |
| `/auth/google/callback` | GET | OAuth 回调（state CSRF） |
| `/auth/google/complete` | POST | 邀请码 gate 时补单 |
| `/admin/auth-config` | GET/PATCH | 管理员切换 `allow_oauth_signup_without_invite` 等 3 开关 |

**SSE 事件新增**
- `harness_event.plugin_manifest_ready`：plugin_builder Agent 完整度打分 ≥ 0.8 且检测到 YAML fence 时 executor 自动 emit。data: `{manifest_yaml, completeness: {维度打分}}`。前端 `PluginsPage` 监听后弹"保存到插件库"模态框。
- `harness_event.turn_complete` 现已**可靠触发**（此前因 audit_logs.created_at 无默认 + post_turn 嵌在 tool_use 分支导致 500 + 纯文本回复跳过，已在 `587857a` 根因级修复）

**运维**
```bash
docker compose up -d              # 启动
admin@prism.dev / PrismAdmin!2026  # 默认管理员
bash scripts/final-ops-smoke.sh   # 9 phase 全栈回归
cd e2e && npx playwright test --project=desktop-chromium   # 桌面 E2E
cd e2e && npx playwright test --project=mobile-safari       # 移动 E2E
```

---

## 0. TL;DR

| 项 | 值 |
|---|---|
| API base | `http://<host>/api/v1` |
| Auth | `Authorization: Bearer <access_token>` |
| Access token TTL | 15 分钟 |
| Refresh | HttpOnly cookie，走 `POST /auth/refresh` 换新 access |
| SSE | `GET /sessions/{id}/stream?ticket=<TICKET>` 一次性票 60s |
| 实时流 | SSE（Redis publish-subscribe 转发） |
| 总路由 | 83 endpoints |
| 错误上报 | `POST /frontend-errors`（免认证，60/IP/min） |

**最小集成清单**（chat MVP 只需这 7 个）：
1. `POST /auth/login` → 拿 access token + refresh cookie
2. `POST /sessions` → 建 session
3. `POST /tasks` → 提交用户消息
4. `POST /auth/sse-ticket` → 换 SSE 一次性票
5. `GET /sessions/{id}/stream?ticket=...` → 开 SSE 消费流
6. `GET /sessions/{id}/messages` → 初次加载历史消息
7. `POST /sessions/{id}/permission-answer` → 用户回复权限请求

---

## 1. 认证流程（DOC-06）

### 1.1 登录 / 注册

```http
POST /api/v1/auth/login
Content-Type: application/json
{ "email": "user@x.com", "password": "at-least-8-char" }

200 OK
{ "access_token": "<JWT>", "token_type": "bearer", "expires_in": 900 }
Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth/refresh
```

```http
POST /api/v1/auth/register
{ "email": "u@x.com", "username": "alice", "password": "...", "invite_code": "PRISM-ABCD1234" }
```

### 1.2 Token 续期

```http
POST /api/v1/auth/refresh
Cookie: refresh_token=<cookie from login>

200 { "access_token": "<new JWT>", ... }
```

**实现提示**：前端应在 access token 剩余 ≤2 分钟时异步调用 `/auth/refresh`，拿到新 token 后替换。refresh cookie 由浏览器自动管理。

### 1.3 退出

```http
POST /api/v1/auth/logout
```
服务端清 cookie；前端同步清 access token 内存。

### 1.4 当前用户

```http
GET /api/v1/auth/me  →  UserResponse
```

```ts
interface UserResponse {
  id: string;           // UUID7
  email: string;
  username: string;
  role: "user" | "admin";
  avatar_url: string | null;
  last_login_at: string | null;  // ISO 8601
  created_at: string;
}
```

### 1.5 SSE 一次性票（`ADR-057`，陷阱 #4）

**重要**：SSE 认证**不得**把 JWT 放 URL query（浏览器 history / referer 会泄露）。流程：

```
前端: POST /auth/sse-ticket  { "session_id": "<uuid>" }
     → 带 Authorization: Bearer <access_token>
响应: { "ticket": "<60s一次性 token>", "expires_in": 60 }

前端: new EventSource(`/api/v1/sessions/<id>/stream?ticket=<ticket>`)
后端: Redis GETDEL ticket key → 验通过开流
```

Ticket **一次性**消费（GETDEL），不可复用。过期/重放 → 401。

---

## 2. 主业务流（Session → Task → Run → Stream）

### 2.1 Session 管理（DOC-07 Task 7.1）

| Method | Path | 用途 |
|---|---|---|
| POST | `/sessions` | 创建 session |
| GET | `/sessions` | 列出我的 sessions |
| GET | `/sessions/{id}` | 详情 |
| PATCH | `/sessions/{id}` | 改标题 / pin / config |
| DELETE | `/sessions/{id}` | 软删 |
| GET | `/sessions/{id}/messages?after_sequence_no=N&limit=50` | 消息分页（增量） |
| GET | `/sessions/{id}/runs` | 该 session 下所有 Run |
| GET | `/sessions/{id}/queue` | 当前排队任务 |
| DELETE | `/sessions/{id}/queue/{item_id}` | 取消某条排队 |

```ts
interface SessionResponse {
  id: string;
  title: string | null;
  status: "idle" | "running" | "queued";
  blocking_run_id: string | null;       // running 时的 run_id
  config_snapshot: Record<string, any>;
  is_pinned: boolean;
  pinned_at: string | null;
  im_channel: string | null;             // "feishu"|"wecom"|"telegram"|null
  im_chat_id: string | null;
  message_count: number;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

interface MessageResponse {
  id: string;
  run_id: string | null;
  role: "user" | "assistant" | "tool_use" | "tool_result" | "system";
  content: Array<ContentBlock>;  // 见 §9.2
  text_preview: string | null;
  sequence_no: number;           // 严格单调递增(per-session advisory_xact_lock)
  created_at: string;
}
```

### 2.2 提交任务（DOC-07 Task 7.2）

```http
POST /api/v1/tasks
{ "session_id": "<uuid or null>", "prompt": "用户输入内容", "agent_type": null }

202 {
  "session_id": "...",
  "run_id": "..." | null,            // 排队时为 null
  "accepted_type": "immediate" | "queued_query",
  "queue_position": null | number    // 排队时的位置
}
```

- `session_id=null` → 后端自动建新 session
- `agent_type=null` → TaskRouter 自动路由（关键词匹配 → general/explore/planner/verifier/plugin_builder，复杂任务 → coordinator 模式）
- `accepted_type=immediate` → 立即启动子进程，**请立即订阅 SSE**
- `accepted_type=queued_query` → session 忙，排队中；前端可轮询 `GET /sessions/{id}/queue` 或等 SSE `queue_promoted` 事件

### 2.3 Run 管理（DOC-07 Task 7.2/7.4）

| Method | Path | 用途 |
|---|---|---|
| GET | `/runs/{id}` | Run 详情 |
| POST | `/runs/{id}/cancel` | 取消（3 模式） |
| POST | `/runs/{id}/resume` | 崩溃后恢复（Coordinator 用） |

```ts
interface CancelRunRequest {
  mode: "graceful" | "force" | "also_cancel_queue";
  // graceful: SIGTERM, 完成当前 tool 后停
  // force: SIGKILL 立即
  // also_cancel_queue: graceful 当前 + 取消后续队列
}

interface RunResponse {
  id: string;
  session_id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "timeout";
  model: string;
  provider_id: string | null;
  schedule_mode: string;
  agent_type: "general" | "explore" | "planner" | "verifier" | "coordinator" | "plugin_builder" | null;
  error_message: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  turn_count: number | null;
  harness_summary: Record<string, any> | null;  // 含 cache_hit_tokens / cache_creation_tokens / compactions / ...
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}
```

### 2.4 SSE 流（核心实时通道）

```javascript
const { ticket } = await post('/auth/sse-ticket', { session_id });
const es = new EventSource(`/api/v1/sessions/${session_id}/stream?ticket=${ticket}`);

es.addEventListener('message', (e) => {
  const evt = JSON.parse(e.data);
  switch (evt.type) {
    case 'text_delta': appendText(evt.message_id, evt.text); break;
    case 'tool_use_delta': appendToolInput(evt.tool_use_id, evt.partial_json); break;
    case 'tool_start': renderToolCall(evt); break;
    case 'tool_end': finalizeToolCall(evt); break;
    case 'message_complete': finalizeMessage(evt); break;
    case 'run_complete': markRunDone(evt); break;
    case 'run_error': showError(evt.error); break;
    case 'run_crashed': showCrashDialog(evt); break;
    case 'permission_ask': showPermissionDialog(evt); break;  // 见 §2.5
    case 'harness_event': handleHarnessEvent(evt); break;     // 见 §8.2
    case 'coordinator_plan_update': updatePlanUI(evt); break; // 见 §2.6
    case 'session_title': updateSessionTitle(evt.title); break;
  }
});
```

SSE 最多每 session 同时 **3 个连接**（Backend 限）。断线后前端指数退避 + 续接：重连时带 `Last-Event-ID` 头，后端会补发 stream buffer 最近 200 条。

### 2.5 权限询问（ADR-028 / ADR-064）

当子进程需要用户批准敏感工具（bash / Write / WebFetch / skill_install）时：

```
SSE event:
{
  "type": "permission_ask",
  "request_id": "uuid7",
  "tool_name": "bash",
  "tool_input": { "command": "rm -rf ..." },
  "reason": "bash 命令可能破坏文件系统",
  "timeout_at": "2026-04-19T12:34:56Z"  // 超时后默认 deny
}

前端弹框 → 用户点击 allow/deny →
POST /sessions/{session_id}/permission-answer
{ "request_id": "uuid7", "decision": "allow" | "deny" }
```

后端 RPUSH 到 Redis → 子进程 BLPOP 拿到答案继续。若超时（默认 60s）→ 自动 deny。

### 2.6 Coordinator Plan（ADR-040）

复杂任务走 Coordinator 模式：

```
SSE events sequence:
1. { "type": "coordinator_plan_update", "plan_json": {...}, "current_step": 0, "total_steps": 5, "status": "running" }
2. { "type": "harness_event", "subtype": "step_start", "detail": { "step_id": 1 } }
3. [normal run events from sub-agent]
4. { "type": "harness_event", "subtype": "step_end", "detail": { "step_id": 1, "status": "completed" } }
5. { "type": "coordinator_plan_update", "current_step": 1, ... }
... 重复 2-5 每 step
N. { "type": "coordinator_plan_update", "status": "completed" }
```

前端 UI：进度条 `current_step / total_steps`，展开显示 `plan_json.steps[]` 每步状态。

**崩溃恢复**：后端 HeartbeatMonitor 超 30s 无心跳 → 标 run `crashed` → SSE 发 `run_crashed` → 前端显示"恢复"按钮 → `POST /runs/{id}/resume`。

---

## 3. 管理后台（DOC-06 Task 6.2 / DOC-09 Task 9.3）

**权限**：所有 `/admin/*` 端点需 `role=admin`，前端应按 `GET /auth/me.role` 条件渲染菜单。

| Method | Path | 用途 |
|---|---|---|
| GET | `/admin/users?page=1&search=x` | 用户列表（分页 + 搜索） |
| PATCH | `/admin/users/{id}` | 改用户（禁用 / 角色） |
| PATCH | `/admin/users/{id}/role` | 仅改角色 |
| DELETE | `/admin/users/{id}` | 禁用（`is_active=false`，不硬删） |
| POST | `/admin/invite-codes` | 创建邀请码 |
| GET | `/admin/invite-codes` | 列出 |
| DELETE | `/admin/invite-codes/{id}` | 撤销 |
| GET | `/admin/audit-logs?action=...&user_id=...&limit=100` | 审计 |
| GET | `/admin/audit-logs/export` | CSV 导出（≤10k） |
| GET | `/admin/stats/dashboard` | 系统总览（users/sessions/runs/providers/harness 健康） |
| GET | `/admin/usage?group_by=day\|week\|month` | 全系统用量聚合 |
| GET | `/admin/alerts/config` | 查告警配置（IM / email / threshold） |
| PATCH | `/admin/alerts/config` | 改告警配置 |

**安全约束**（ADR-083）：不可降级**最后一个 admin**（409）；不可禁用**自己**（409）。

邀请码格式：`PRISM-XXXXXXXX`（8 位大写字母数字）。

---

## 4. 用户资产

### 4.1 Providers（模型供应商，DOC-02 Task 2.3 / DOC-09 Task 9.2）

| Method | Path | 用途 |
|---|---|---|
| GET | `/providers` | 我可见的 providers（system preset + 我自己的） |
| GET | `/providers/presets` | 8 个内置预设（Anthropic/OpenAI/DeepSeek/Kimi/Qwen/...） |
| POST | `/providers` | 创建 user-scoped provider（api_key 会 AES-256-GCM 加密） |
| PUT | `/providers/{id}` | 改 |
| DELETE | `/providers/{id}` | 删 |
| POST | `/providers/{id}/test` | 探测 capabilities（prompt_cache / vision / ...） |
| GET | `/providers/usage?group_by=day&start_date=...&end_date=...` | 用量（含 cache tokens 三字段） |

**特性**：
- api_key 写入时服务器即加密；响应中返回掩码 `sk-1...abcd`
- `is_healthy` 字段实时从 Redis `harness:circuit:{id}` 读（熔断器状态，ADR-013）
- 用量含 `cache_hit_tokens` / `cache_creation_tokens` / `cache_hit_ratio` / `estimated_cache_savings_usd`

### 4.2 MCP Servers（DOC-09 Task 9.1 / DOC-05 Task 5.2）

| Method | Path | 用途 |
|---|---|---|
| GET | `/mcp-servers` | MCP server 定义（system + user） |
| POST | `/mcp-servers` | 创建 |
| DELETE | `/mcp-servers/{id}` | 删 |
| POST | `/mcp-servers/{id}/test` | 探测 capabilities |
| GET | `/mcp-installs` | 我已安装的 MCP |
| POST | `/mcp-installs` | 安装 |
| PATCH | `/mcp-installs/{id}` | 改启用状态 / 用户 config |
| DELETE | `/mcp-installs/{id}` | 卸载 |

MCP 工具名固定格式 `mcp__{server}__{tool}`（ADR-049）。

### 4.3 Skills（DOC-05 Task 5.5/5.6）

| Method | Path | 用途 |
|---|---|---|
| GET | `/skills/search?q=...&source=local\|github` | 两源并行搜索 |
| POST | `/skills/install` | 安装 |
| GET | `/skills/installed` | 已安装 |
| GET | `/skills/{name}` | 详情 |
| POST | `/skills/{name}/update` | 更新到新版 |
| DELETE | `/skills/{name}` | 卸载 |

**重要**（ADR-052）：Agent 工具 `skills_search` **仅搜索，不安装** — 安装必须走用户明确批准（本组 API）。

Skill 加载三级模式（ADR-043）：
- Level 0：注册（描述索引，0 token）
- Level 1：frontmatter 描述注入 system prompt（~50 tokens）
- Level 2：按需完整加载到 messages（`is_skill_context=true` 标记，Compaction 保护）

### 4.4 Plugins（DOC-05 Task 5.4 / 5.7）

| Method | Path | 用途 |
|---|---|---|
| POST | `/plugins/load` | 加载 plugin（解析 plugin.yaml） |
| POST | `/plugins/validate` | 校验 plugin.yaml 格式 |
| POST | `/plugins/export-cc` | 导出为 Claude Code `.claude/` zip（含 ConversionReport） |

ConversionReport 包含 `lost_fields[]` + `warnings[]`（PRD 约定：Prism→CC 不对称）。

---

## 5. IM 集成（DOC-08）

| Method | Path | 用途 |
|---|---|---|
| GET | `/im/channels` | 飞书 / 企微 / Telegram 3 通道配置 |
| PATCH | `/im/channels/{channel}` | 改配置（密钥 / 启用） |
| POST | `/im/webhook/feishu` | 飞书 webhook 接入（平台侧 POST） |
| POST | `/im/webhook/wecom` | 企微 |
| GET | `/im/webhook/wecom` | 企微 URL 验证 |
| GET | `/im/bindings` | 我的 IM 绑定 |
| POST | `/im/bindings/pair` | 生成配对码（6 位 5min TTL） |
| DELETE | `/im/bindings/{id}` | 解绑 |

**绑定流程**：
1. 用户在前端 `POST /im/bindings/pair` → 拿到 `PAIR-XXXXXX`
2. 在 IM 中发给 Prism Bot：`/bind PAIR-XXXXXX`
3. 后端验证 + 写 `im_bindings`（三元组 channel+platform_user_id+platform_chat_id 唯一）

---

## 6. 观测与健康

### 6.1 Health（K8s probe，ADR-114）

| Path | 用途 |
|---|---|
| `/api/v1/health/live` | 存活探针（无依赖检查，100% 快） |
| `/api/v1/health/ready` | 就绪（检查 DB + Redis，不ready 返 503） |
| `/api/v1/health/detailed` | 详细（admin only；uptime + 组件 health + 资源百分比） |
| `/health/live` `/health/ready` | 同上别名（便于 K8s 默认路径） |
| `/metrics` | Prometheus 抓取（68 个 prism_* 指标，免认证） |

### 6.2 Harness Analytics（DOC-12 Task 12.2）

| Path | 用途 |
|---|---|
| `/harness/config` | 有效配置（2 源合并：default + yaml） |
| `/harness/analytics?window=7d` | 跨 run 聚合（turns / cache_stats / route_distribution） |
| `/harness/entropy-check` | 运行熵检测（8 信号） |
| `/harness/threshold-calibrate` | 阈值自动校准（EMA 建议） |

---

## 7. 前端错误上报（DOC-12 Task 12.7，ADR-119）

**对前端最关键**：实现 ErrorBoundary + window.onerror + unhandledrejection 时统一调本端点。

```http
POST /api/v1/frontend-errors
Content-Type: application/json
（免认证！登录页崩溃也能上报）

{
  "message": "Cannot read property 'x' of undefined",
  "stack": "TypeError: ...",
  "name": "TypeError",
  "url": "https://app/chat",
  "user_agent": "Mozilla/5.0 ...",
  "viewport": "1920x1080",
  "user_id": "<uuid or null>",
  "session_id": "<uuid or null>",
  "context": { "action": "send_message", "extra": "..." },
  "severity": "error",                    // info|warning|error|critical
  "timestamp": "2026-04-19T12:34:56.789Z"
}

204 No Content
```

**限流**：60 次/IP/min（Redis SETNX + EXPIRE），超限 429。
**Severity** → Prometheus `prism_frontend_errors_total{severity,viewport}` + structlog 分级记录 + audit_logs。

---

## 8. 实时事件字典（SSE 完整清单）

### 8.1 顶层事件类型（`evt.type`）

| type | 频率 | 字段 | 用途 |
|---|---|---|---|
| `text_delta` | 高频（流式文字每 chunk） | `message_id`, `text`, `ts` | assistant 消息文字增量 |
| `tool_use_delta` | 高频 | `tool_use_id`, `partial_json`, `ts` | 工具入参 JSON 流式 |
| `tool_start` | 中频 | `tool_use_id`, `tool_name`, `input` | 工具开始 |
| `tool_end` | 中频 | `tool_use_id`, `output`, `is_error`, `duration_ms` | 工具结束（output preview 500 字） |
| `message_complete` | 每消息一次 | `role`, `content`, `sequence_no_hint` | 消息完整体 |
| `run_complete` | 结束 | `input_tokens`, `output_tokens`, `cache_hit_tokens`, `cache_creation_tokens`, `turn_count` | Run 正常完成 |
| `run_error` | 结束 | `error` | Run 失败 |
| `run_crashed` | 结束（异常） | `run_id`, `reason` | 心跳超时 / OOM / 主机重启 |
| `permission_ask` | 稀疏 | `request_id`, `tool_name`, `tool_input`, `reason`, `timeout_at` | 需用户批准（见 §2.5） |
| `harness_event` | 中频 | `subtype`, `detail` | 子事件（见 8.2） |
| `coordinator_plan_update` | Coordinator 模式 | `plan_json`, `current_step`, `total_steps`, `status`, `step_results` | 计划进度 |
| `session_title` | 偶尔 | `title` | session 自动命名 |

### 8.2 `harness_event` 子类型（`evt.subtype`）

| subtype | detail 字段 | 用途 |
|---|---|---|
| `turn_complete` | `{ turn, duration_ms, tool_calls }` | 每 turn 结束 |
| `compaction` | `{ tier, before_tokens, after_tokens }` | 上下文压缩触发（Tier 1/2/4） |
| `loop_detected` | `{ repeat_count, fingerprint }` | 循环检测 |
| `step_start` / `step_end` | `{ step_id, status }` | Coordinator step |
| `fork_start` / `fork_end` | `{ agent_type, goal, capabilities, depth, turn_count, success }` | Fork 子 Agent |
| `plan_step` | `{ step_id, type, description }` | 初始 plan 广播 |
| `permission_ask_timeout` | `{ request_id }` | 权限询问超时 |
| `user_memory_extracted` | `{ content, source_session_id, source_run_id }` | session 结束提炼记忆 |
| `queue_promoted` | `{ promoted_run_id }` | 排队→运行晋升 |

前端可按 subtype 决定是否展示 UI（`turn_complete` 通常不展示，`compaction` 可加提示）。

---

## 9. 关键数据结构（Data Shapes）

### 9.1 认证相关

见 §1 的 `TokenResponse`, `UserResponse`.

### 9.2 消息内容 Block（PrismMessage canonical，ADR-007）

`MessageResponse.content` 是 `ContentBlock[]`，联合类型：

```ts
type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, any> }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean }
  | { type: "image"; source: { type: "base64"|"url"; data: string; media_type?: string } }
  | { type: "thinking"; thinking: string };  // extended_thinking
```

**规范**：
- `role="user"` 只含 `text_block` / `tool_result_block` / `image_block`
- `role="assistant"` 只含 `text_block` / `tool_use_block` / `thinking_block`
- **绝不**构造 `role="tool"` / `role="system"`（ADR-007）

### 9.3 Plan（Coordinator）

```ts
interface Plan {
  task_summary: string;
  steps: PlanStep[];
}

interface PlanStep {
  step_id: number;
  description: string;
  agent_type: "general" | "explore" | "planner" | "verifier";
  task_prompt: string;
  depends_on: number[];
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  result: string;
}
```

### 9.4 Provider

```ts
interface ProviderResponse {
  id: string;
  name: string;
  protocol: "anthropic" | "openai";
  scope: "system" | "user";
  user_id: string | null;
  base_url: string;
  model_list: string[];
  is_default: boolean;
  priority: number;
  api_key_masked: string;        // "sk-1...abcd"
  config: {
    capabilities: {
      prompt_cache: boolean;
      streaming_tools: boolean;
      extended_thinking: boolean;
      vision: boolean;
    };
  };
  is_healthy: boolean | null;    // from Redis circuit breaker
  created_at: string;
}
```

---

## 10. 错误与 HTTP 语义

### 10.1 统一响应包装

成功：
```json
{ "data": {...} }   // 或直接返回 schema（部分端点）
```

错误（FastAPI 自动）：
```json
{ "detail": "human-readable message" }
// 或 Pydantic 验证错误：
{ "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }
```

### 10.2 常见状态码

| Code | 语义 |
|---|---|
| 200 | 成功 |
| 201 | 创建成功 |
| 202 | 已受理，异步处理中（`POST /tasks`） |
| 204 | 成功无响应体（`POST /frontend-errors`） |
| 400 | Bad Request（业务层） |
| 401 | Token 无效 / 过期 / SSE ticket 已用 |
| 403 | 无权限（非 admin / 非 owner） |
| 404 | 资源不存在 |
| 409 | 状态冲突（Run 已结束不可 cancel；最后一个 admin 不可降级） |
| 422 | Pydantic 校验失败 |
| 429 | Rate limit（`/frontend-errors` 60/IP/min） |
| 503 | 依赖不可用（`/health/ready` DB 或 Redis down） |

### 10.3 SSE 连接异常

| 情况 | 处理 |
|---|---|
| ticket 过期/已用 | 401 → 重新换票重连 |
| 后端重启 | 连接断开 → 前端指数退避（1s,2s,4s,...） |
| session 已结束但前端还在订阅 | 收到 `run_complete` / `run_error` 后主动 `es.close()` |

---

## 11. 前端开发提示（v4 版踩坑合集）

1. **绝不**把 JWT 放 SSE URL query（陷阱 #4），必须用一次性 ticket
2. SSE 同一 session **最多 3 连接**（Backend 限），多 tab 时需协调或关旧连接
3. `text_delta` 超高频（每 token 一次），前端必须**批处理 + requestAnimationFrame** 或 **节流 100ms** 刷新 DOM，否则卡顿
4. `tool_use_delta.partial_json` 是**流式累积**的 JSON 字符串片段，不是合法 JSON，拼完整后（看 `tool_start` 的 `input` 字段才是最终值）再 parse
5. `message_complete.sequence_no_hint` 只是 hint，权威值由 DB 分配（见 `GET /messages` 的 `sequence_no`）
6. Coordinator 模式下前端应展示 plan 进度条 + 折叠每步 fork 子 agent 日志（避免刷屏）
7. 权限弹框 60s 超时前端也要显示倒计时；超时自动隐藏+刷消息流（因后端已 deny）
8. IM 相关的 admin 页 + 配对流程是 2026 年新特性，可放在"设置 > 集成"独立子页
9. 错误上报 payload 超大会截断：`message ≤500 / stack ≤2000`，前端最好自行截
10. `/health/*` 和 `/metrics` **免认证**，生产环境应通过 nginx 只允许内网/监控系统访问

---

## 12. 文件位置速查（看代码时用）

| 功能 | 后端位置 |
|---|---|
| Auth | `backend/app/api/v1/auth.py`, `services/auth_service.py`, `services/sse_ticket_service.py` |
| Sessions | `backend/app/api/v1/sessions.py`, `services/session_service.py` |
| Tasks / Runs | `backend/app/api/v1/tasks.py`, `runs.py`, `services/task_service.py`, `run_lifecycle.py`, `session_queue.py`, `sequence_service.py` |
| Subprocess | `backend/app/services/process_manager.py`, `coordinator_recovery.py` |
| Callback 接收 | `backend/app/api/v1/internal.py`, `services/callback_service.py` |
| SSE | `backend/app/services/sse_manager.py` |
| Heartbeat | `backend/app/services/heartbeat_monitor.py` |
| Admin | `backend/app/api/v1/admin.py`, `services/audit_service.py`, `admin_stats_service.py` |
| Providers | `backend/app/api/v1/providers.py`, `services/provider_service.py` |
| MCP | `backend/app/api/v1/mcp.py`, `services/mcp_service.py` |
| Skills | `backend/app/api/v1/skills.py`, `services/skill_install_service.py` |
| Plugins | `backend/app/api/v1/plugins.py` |
| IM | `backend/app/api/v1/im.py`, `services/im_gateway.py`, `im_feishu.py`, `im_wecom.py`, `im_telegram.py`, `im_binding_service.py`, `im_dedup.py` |
| Health | `backend/app/api/v1/health.py` |
| Frontend errors | `backend/app/api/v1/frontend.py` |
| Harness Analytics | `backend/app/api/v1/harness.py`, `services/harness_analytics.py`, `entropy_detector.py` |
| Alerts | `backend/app/services/alert_dispatcher.py`, `resource_monitor.py` |
| Observability | `backend/app/observability/{metrics,tracing,logging}.py` |

| Agent 子进程 | 位置 |
|---|---|
| TAOR 主循环 | `executor/engine/query_engine.py` |
| 工具执行 | `executor/tools/pipeline.py`, `registry.py`, `builtin/` |
| Harness | `executor/harness/lifecycle.py`（HarnessRuntime 总装） |
| Middleware 4 钩点 | `executor/harness/middleware/{loop_detection,observability,feedback_capture}.py` |
| Hook | `executor/harness/hooks/{system,decision,handlers,events}.py` |
| Permission | `executor/harness/permissions/{engine,ask_protocol,guardrails}.py` |
| Compaction | `executor/engine/compaction.py` |
| Memory | `executor/engine/memory.py` |
| Agents 6 种 | `executor/agents/{general,research,planner,verifier,coordinator,plugin_builder}.py` + `pool.py` |
| Coordinator | `executor/coordinator/{coordinator,fork_manager,plan,fork_briefing,fork_result}.py` |
| Plugins | `executor/plugins/{skill_loader,mcp_client,host,namespace,plugin_types,skills_registry,cc_compat}.py` |
| Router | `executor/router.py` |
| Entry | `executor/__main__.py` |

---

## 13. 快速开始（10 分钟起步）

```javascript
// 1. 登录
const loginRes = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',  // 接 refresh cookie
  body: JSON.stringify({ email, password })
});
const { access_token, expires_in } = await loginRes.json();

// 2. 建 session
const sess = await fetch('/api/v1/sessions', {
  method: 'POST',
  headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: '新对话' })
}).then(r => r.json());

// 3. 提交 prompt
const task = await fetch('/api/v1/tasks', {
  method: 'POST',
  headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: sess.id, prompt: '你好' })
}).then(r => r.json());

// 4. 换 SSE ticket 开流
const { ticket } = await fetch('/api/v1/auth/sse-ticket', {
  method: 'POST',
  headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: sess.id })
}).then(r => r.json());

const es = new EventSource(`/api/v1/sessions/${sess.id}/stream?ticket=${ticket}`);
es.onmessage = (e) => {
  const evt = JSON.parse(e.data);
  if (evt.type === 'text_delta') console.log(evt.text);
  if (evt.type === 'run_complete') es.close();
};
```

---

## 14. 下一步（前端实施参考）

前端对应的 DOC-10 / DOC-11 尚未实施（用户明确不做），但设计文档已齐全：
- `PRD_V4/DOC-10-v4.md` — 设计系统 + useSSE hook + apiClient + ErrorBoundary
- `PRD_V4/DOC-11-v4.md` — 对话界面 / 会话管理 / 设置页 / 用量仪表盘 / Skills / Admin Observability

共 10 个 Task，可按需选做。
