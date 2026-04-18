# Prism v2 架构 Review — Batch 4: Frontend 层

> **范围**: DOC-10 (Frontend Foundation) / DOC-11 (Frontend Features) + 2026-04-07 UI design spec + Task 11.5
> **立场**: 质量优先、Claude.ai 视觉语言、Poco 功能完整保留、桌面+移动端双视口
> **评审者**: Claude Opus 4.7

---

## 0. 整体判断

Frontend 三份文档的质量分布:

- **DOC-10 Foundation**: 过于简略(322 行),三个 Task 的 Part B 实现规范严重不足,Sonnet 4.6 拿这份根本没法直接写代码。**必须大幅填充**
- **DOC-11 Features**: 中等。Task 11.1/11.4/11.5 有较充实的组件清单和 wireframe,但 Task 11.2/11.3 只有几行,缺细节
- **UI design spec (2026-04-07)**: 质量**最高**,968 行,设计 token / 字体 / 主题 / Agent Panel / TaskComposer / Capabilities Platform 全部到位。这份和 DOC-10/11 是**两份并列的真相源**,而不是 DOC-10/11 的参考

**关键问题**: DOC-10/11 和 UI design spec 的**关系在文档里没说清**。Sonnet 4.6 拿到手,不知道哪份优先级高、哪份是 authoritative。

Batch 4 最严重的 5 个问题:

| # | 问题 | 影响 |
|---|---|---|
| **B4-1** | **DOC-10 Task 10.2 / 10.3 Part B 严重不足** | SSE 客户端和 API 客户端是所有前端功能的基石,细节不足会导致整个前端构建链出问题 |
| **B4-2** | **DOC-10/11 vs UI design spec 的优先级未定义** | 两份文档对同一组件有不同描述(比如 Task 11.1 的 ChatHeader vs UI design §6 的双态布局),Sonnet 会困惑 |
| **B4-3** | **Batch 2/3 新增的前端需求全部缺失** | permission_ask 弹窗、coordinator Plan 可视化、SSE ticket、tab 限制、回调协议变更后的 SSE 结构变化 —— DOC-11 里全部没体现 |
| **B4-4** | **SSE 事件处理的状态机和消息 merge 策略不清** | text_delta 如何 merge 到 message、tool_use_delta 如何拼接工具参数、message_complete 如何替换 streaming 消息 —— Sonnet 拿这份会每个 handler 都自己猜 |
| **B4-5** | **Poco 的 424 个文件完整保留 vs 前端体积 < 10MB 矛盾** | 用户要求 Poco 功能一个都不能少,但前端体积 < 10MB 源码,UI design 说"参考 Poco 68 文件架构完整保留"—— 实际取舍没定义 |

下面按 Part A / B / C 展开。

---

## Part A — 实现级审视

### DOC-10: Frontend Foundation

#### A10-1. Task 10.1 设计 token 和 UI design spec 重复/冲突

DOC-10 Task 10.1 里写:
```
配色：暖白背景 #FAFAF8、深灰文字 #1A1A1A、强调色 #D97706(琥珀)
字体：标题衬线体(Noto Serif SC / Georgia 回退)、正文无衬线(Inter / system-ui)
间距：8px 基准网格
```

UI design spec §2 里写:
```css
--color-brand: #c96442;     /* Terracotta */
--color-warning: #B8860B;   /* 琥珀暖黄 */
...
--spacing-unit: 8px;
```

**色值冲突**: DOC-10 说品牌色 `#D97706`(琥珀),UI design 说 `#c96442`(Terracotta),**完全不同的色**。DOC-10 说暖白背景 `#FAFAF8`,UI design 里背景色在主题变量里,三套主题(Prism/Light/Dark)各不同。

**修法(改写阶段落地)**: 删除 DOC-10 Task 10.1 里的具体色值字体描述,改为"**设计 token 系统详见 2026-04-07 UI design spec §2-§4,本 Task 负责将该规范转换为 Tailwind config + CSS variables 实现**"。UI design spec 是**视觉真相源**,DOC-10 是**实现规范**,两者职责分离。

#### A10-2. Task 10.2 SSE 客户端的关键细节全部缺失 (B4-4)

Part B 只说"按事件类型分发到不同 handler",具体的 **状态机**、**消息 merge 策略**、**重连恢复语义** 都没写。Sonnet 4.6 拿这份直接写代码会出 bug。

**必须补齐的细节**:

**1. text_delta merge 到 assistant message**:
```typescript
// Zustand store 中的消息状态机:
interface ChatStore {
  messages: Message[];            // 已完成持久化的消息
  streamingMessage: {              // 当前正在 streaming 的消息(单条)
    runId: string;
    role: "assistant";
    content: ContentBlock[];       // 可能有多个 block: text + tool_use
    currentTextBlock?: TextBlock;  // 当前正在累加的 text block
  } | null;
}

// text_delta handler:
function onTextDelta(data: { text: string }) {
  if (!state.streamingMessage) {
    state.streamingMessage = createNew();
  }
  if (!state.streamingMessage.currentTextBlock) {
    state.streamingMessage.currentTextBlock = { type: "text", text: "" };
    state.streamingMessage.content.push(state.streamingMessage.currentTextBlock);
  }
  state.streamingMessage.currentTextBlock.text += data.text;
}

// tool_use_start handler:
function onToolUseStart(data: { tool_use_id, tool_name, ... }) {
  // 结束当前 text block(下次 text_delta 开新的)
  state.streamingMessage.currentTextBlock = undefined;
  // 加 tool_use block
  state.streamingMessage.content.push({
    type: "tool_use",
    id: data.tool_use_id,
    name: data.tool_name,
    input: {},  // 等 tool_use_delta 填充
    _streaming_input_json: "",  // 内部字段,累积 JSON
  });
}

// tool_use_delta handler:
function onToolUseDelta(data: { tool_use_id, tool_input_delta }) {
  const block = state.streamingMessage.content.find(b => 
    b.type === "tool_use" && b.id === data.tool_use_id
  );
  if (block) {
    block._streaming_input_json += data.tool_input_delta;
    // 可选: 尝试 partial JSON parse 显示用户
  }
}

// tool_use_end handler (来自 tool_use_end SSE 或 tool_start HTTP callback):
function onToolUseEnd(data: { tool_use_id, tool_input_complete }) {
  const block = state.streamingMessage.content.find(b => b.id === data.tool_use_id);
  if (block) {
    block.input = data.tool_input_complete;
    delete block._streaming_input_json;
  }
}

// message_complete handler(Batch 3 §A7-4 新事件):
function onMessageComplete(data: { message: Message }) {
  // 后端持久化完毕,推来完整消息
  state.messages.push(data.message);
  state.streamingMessage = null;  // 清空 streaming
}
```

**2. 断线重连的消息恢复语义**:

原 EventSource 会自动重连,但**中间丢失的事件怎么办?**

Batch 3 §A7-4 提到 "message_complete 携带完整消息一次性落 DB"。前端重连后:
1. SSE 重连
2. 前端调 `GET /sessions/{id}/messages?after_message_id=xxx` 拉增量
3. 把拉到的消息 append 到 state.messages
4. 继续接收新 SSE 事件

实现上:
```typescript
class SSEClient {
  async reconnect() {
    await this.fetchIncrementalMessages();  // 先补齐
    this.openEventSource();                  // 再连
  }
  
  private lastKnownMessageId: string | null = null;
  
  async fetchIncrementalMessages() {
    if (!this.lastKnownMessageId) return;
    const response = await apiClient.get(
      `/sessions/${this.sessionId}/messages?after_message_id=${this.lastKnownMessageId}`
    );
    for (const msg of response.data.items) {
      chatStore.appendMessage(msg);
      this.lastKnownMessageId = msg.id;
    }
  }
}
```

**3. Token 过期时的处理**:

```typescript
class SSEClient {
  private onEventSourceError = async (event: Event) => {
    if (this.eventSource.readyState === EventSource.CLOSED) {
      // 检查是否 token 过期
      try {
        await apiClient.post("/auth/refresh");
        // 刷新成功,重连 SSE
        await this.reconnect();
      } catch {
        // 刷新失败,跳转登录
        window.location.href = "/login?from=" + window.location.pathname;
      }
    }
  };
}
```

#### A10-3. Task 10.2 Batch 3 新增 SSE 事件的前端处理 (B4-3)

Batch 3 §A7-4 定义了新的事件分类:
- STREAMING_EVENTS: `text_delta` / `tool_use_start` / `tool_use_delta` / `heartbeat`
- CRITICAL_EVENTS: `tool_start` / `tool_end` / `harness_event` / `run_complete` / `run_error` / `session_title` / `permission_ask` / `message_complete`

DOC-10 当前只列了 11 种事件,**`permission_ask` 和 `message_complete` 缺失**,必须补。

`permission_ask` 的前端处理(Batch 2 B2-1 落地):
```typescript
function onPermissionAsk(data: {
  request_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  reason: string;
  timeout: number;  // 秒
}) {
  // 1. 显示弹窗
  showPermissionAskDialog({
    requestId: data.request_id,
    toolName: data.tool_name,
    toolInput: data.tool_input,
    reason: data.reason,
    onAllow: async () => {
      await apiClient.post(`/sessions/${sessionId}/permission-answer`, {
        request_id: data.request_id,
        decision: "allow",
      });
    },
    onDeny: async () => {
      await apiClient.post(`/sessions/${sessionId}/permission-answer`, {
        request_id: data.request_id,
        decision: "deny",
      });
    },
    timeoutSeconds: data.timeout,
    onTimeout: () => {
      // 系统已 fail-safe 为 deny,前端只提示
      showToast("权限请求已超时,默认拒绝", "warning");
    },
  });
}
```

弹窗 UX:
- 居中对话框,非阻塞(不锁屏幕)
- 展示:工具名、参数(JSON pretty)、为什么需要询问(reason)
- 倒计时显示:"300s 内未回答将自动拒绝"
- 两个按钮:允许(brand 色) / 拒绝(error 色)
- 多个 permission_ask 排队时,用 stack 形式展示,最新的在最上

#### A10-4. Task 10.3 API 客户端 auto-refresh 的竞态

Part B 只说"access_token 过期时自动通过 /auth/refresh 续期"。但**并发请求场景**会出问题:

```
Request A (token 过期) → 发 /auth/refresh
Request B (同时发起) → 没先检查 token → 401
Request B 也去 refresh → 被 refresh token 单次使用限制拒绝
```

**修法 — mutex + 队列**:

```typescript
class ApiClient {
  private refreshPromise: Promise<string> | null = null;  // 全局唯一的 refresh
  
  async request<T>(config: RequestConfig): Promise<ApiResponse<T>> {
    // 如果当前有 refresh 在进行,所有请求都等它完成
    if (this.refreshPromise) {
      await this.refreshPromise;
    }
    
    try {
      return await this._fetch(config);
    } catch (err) {
      if (err.status === 401 && !config._retried) {
        return this.refreshAndRetry(config);
      }
      throw err;
    }
  }
  
  private async refreshAndRetry<T>(config: RequestConfig): Promise<ApiResponse<T>> {
    // 所有并发的 401 请求都走同一个 refreshPromise
    if (!this.refreshPromise) {
      this.refreshPromise = this._doRefresh().finally(() => {
        this.refreshPromise = null;
      });
    }
    
    try {
      await this.refreshPromise;
      config._retried = true;
      return await this._fetch(config);
    } catch {
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }
  
  private async _doRefresh(): Promise<string> {
    const resp = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",  // refresh token 在 httponly cookie
    });
    if (!resp.ok) throw new Error("Refresh failed");
    const { data } = await resp.json();
    authStore.setAccessToken(data.access_token);
    return data.access_token;
  }
}
```

#### A10-5. Task 10.3 SSE ticket 端点流程缺失 (Batch 1 D3 落地)

Batch 1 §3.3 决定了 SSE 改用 ticket 而非 JWT 走 URL。但 DOC-10 Task 10.2 的 SSE 连接仍然是:
```
GET /sessions/{id}/stream?token={JWT}
```

**必须修法**:
```typescript
class SSEClient {
  async connect() {
    // 1. 先获取一次性 ticket
    const { data } = await apiClient.post("/auth/sse-ticket", {
      session_id: this.sessionId,
    });
    
    // 2. 用 ticket 建立 SSE
    this.eventSource = new EventSource(
      `/api/v1/sessions/${this.sessionId}/stream?ticket=${data.ticket}`
    );
  }
  
  async reconnect() {
    this.disconnect();
    await this.fetchIncrementalMessages();
    await this.connect();  // 每次重连获取新 ticket
  }
}
```

### DOC-11: Frontend Features

#### A11-1. Task 11.1 双态布局在 DOC-11 和 UI design 的落差

DOC-11 Task 11.1 的组件架构:
```
ChatPage
├── ChatHeader
├── MessageList
├── QueueIndicator
└── ChatInput
```

UI design §6:
```
对话页面有两种视觉态:
- 对话态(Agent 空闲): 全宽 + 完整 TaskComposer
- 执行态(Agent 运行中): 左侧消息(42rem 收窄) + 右侧 Agent Panel(360px) + 精简 TaskComposer
```

DOC-11 里**完全没有 Agent Panel**的概念,但 UI design 里 Agent Panel 是核心组件。改写阶段必须以 UI design 为准,DOC-11 Task 11.1 整个重写。

额外: DOC-11 里提 `HarnessNotice` 组件(inline in message list),UI design 里也有这个组件。但 UI design 里 **还有 Agent Panel 的 Harness tab**——展示活跃规则 + 事件时间线。两者是**并存关系**(inline 通知 + 面板详情),但 DOC-11 没体现。

#### A11-2. Task 11.1 coordinator Plan 可视化缺失(Batch 2/3 新增)

Batch 2 §A4-3 和 Batch 3 §A7-7 提到 `coordinator_plans` 表。UI design §7 有 Steps tab("Coordinator 模式下显示步骤列表"),但 DOC-11 Task 11.1 只有 `PlanStepList` 一行描述。

**改写阶段必须补**:
- Plan 断点恢复 UI: "检测到未完成的 Coordinator 任务(4/10 step),[继续] [放弃]"
- Plan 进度条: 每个 step 的状态 + 耗时 + token 用量
- Step 失败的错误展示 + 重试按钮
- Plan JSON 的可展开查看(给 power user 看)

#### A11-3. Task 11.4 用量仪表盘的字段和 API 对齐

Task 11.4 说:
```
- 汇总卡片：总 Runs、总 Tokens、总成本
- 按 Provider 的用量饼图
- 按日/周/月的趋势折线图
- 最近 10 次 Run 的详情列表（含 harness_summary 摘要：护栏触发次数、Compaction 次数等）
```

Batch 1 §3.5 schema 补丁加了 `cache_hit_tokens` / `cache_miss_tokens` / `cache_creation_tokens` 字段。仪表盘必须展示 **Prompt Cache 命中率**(这是 Claude.ai 类产品的关键指标,省钱的核心)。

**修法** — 汇总卡片从 3 卡改为 5 卡:
```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ 总 Runs   │ 总 Tokens │ 成本(USD) │ Cache 命中率│ 平均响应时间│
│  42      │ 150K     │ $1.23    │ 67%       │ 3.2s     │
│  +12 vs  │  -5% vs  │ -8% vs   │ ↑5% vs    │ -0.3s vs │
│  昨日    │  昨日    │ 昨日     │ 昨日      │ 昨日     │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

#### A11-4. Task 11.5 Skills 商店的细节与 Batch 2 §C3 修订对齐

Batch 2 §C3 建议:
- Phase 1 只上 Local + GitHub 两个源
- 去重策略明文:按 (name + source) 唯一,不偷偷去重
- 装包时明确展示 source + star 数 + 最后更新时间

DOC-11 Task 11.5 的 SkillCard:
```
│ Skill A  │
│ 描述...  │
│ @manus   │  ← 改为 @github / @local
│ v1.2.0   │
│ [安装]   │
```

**改写阶段补充**:
- 每个 SkillCard 展示 source 标识 + 来源详情(GitHub star、最后更新时间)
- "多个同名 Skill" 的展示:用户看到三个 "web-researcher",分别来自不同源,能各自安装
- 装包前的警告: 来自非官方源的 Skill 显示 ⚠️ "来源未审核"

#### A11-5. Task 11.5 PluginBuilder 向导的阶段感知

UI design 和 DOC-11 Task 11.5 都提到"阶段指示器 + 确认设计按钮",但**阶段感知的数据流**没说清:

Agent 怎么告诉前端"当前阶段是 2,等待设计确认"?

方式 1: SSE `harness_event` 子类型 `plugin_build_phase_change`
方式 2: 消息的 metadata 字段
方式 3: 专门的 Run 状态字段

**质量优先选方式 1**:
```typescript
// Batch 2 P4 扩展的 harness_event subtype:
type HarnessEventSubtype = 
  | "guardrail_trigger"
  | "permission_deny"
  | "permission_ask"
  | "loop_detected"
  | "compaction"
  | "circuit_break"
  | "feedback_alert"
  | "middleware_action"
  | "plugin_build_phase_change";  // ← 新增

// data.detail 携带:
{
  type: "plugin_build_phase_change",
  detail: {
    phase: 2,  // 1-4
    phase_name: "设计方案展示",
    slots_filled: ["target_users", "core_scenarios", "tool_needs"],
    slots_missing: ["boundary_cases", "compliance"],
    ready_for_next: false,
  }
}
```

前端根据这个事件更新阶段指示器和"确认设计"按钮可用性。

#### A11-6. Task 11.2 会话管理缺失的功能

DOC-11 Task 11.2 只有:
```
- 侧边栏会话列表（按 updated_at DESC，置顶优先）
- 会话搜索（按标题和消息预览模糊搜索）
- 会话右键菜单（重命名/置顶/删除）
- 删除确认弹窗
- 新建会话按钮
```

**缺失的功能**(质量优先,非 MVP 思维下必须):
- 会话导出(Markdown / JSON)
- 会话分享(生成只读 URL,含/不含附件)
- 会话 fork(复制当前对话作为新 Session 起点)
- 会话归档(不删除,从列表移到"归档"tab)
- 会话 tag(用户自定义标签,侧边栏按 tag 筛选)
- 多选(批量删除/归档/导出)
- 搜索高级过滤(按 Agent 类型、按日期范围、按是否包含错误)

改写阶段 Task 11.2 必须扩展为完整的 Session 管理能力。这些功能 Poco 都有,Prism 不能少。

#### A11-7. Task 11.3 设置页面的 IM 绑定要和 Batch 3 §A8-4 对齐

Batch 3 §A8-4 建议把配对码从 6 位数字改为 12 位 Base32(`K8M2-XJP9-QR47`)。DOC-11 Task 11.3 的 IM 绑定 UI 必须:
- 配对码显示分段格式,易读
- 复制按钮
- 5 分钟倒计时
- 过期时红色提示 "已过期,请重新生成"
- 生成按钮(生成新码,作废旧码)

### UI Design Spec (2026-04-07)

#### AUI-1. 三套主题(Prism / Light / Dark)的实现复杂度

UI design §4 三套主题。每套主题 6 个表面色变量换掉。**质量优先下保留**,但需要补:

- 主题切换的存储: localStorage 存用户偏好 + DB 存用户设置(跨设备同步)
- 主题自动切换: 根据 `prefers-color-scheme` 系统偏好自动切换 Light/Dark
- 主题切换的无感过渡: CSS transition all 200ms,避免闪烁

#### AUI-2. Capabilities Platform 的 8 个子模块和现有 API 对齐

UI design §10 列出 8 个 Capability 子模块:
1. Skills → 对应 DOC-05 Task 5.5-5.7 + API /skills/*
2. Plugins → 对应 DOC-05 Plugin Ecosystem,**但 /plugins API 在 DOC-01 里不存在**
3. MCP Servers → 对应 DOC-09 Task 9.1
4. Slash Commands → **完全新功能**,后端没有对应 API
5. Sub Agents → 对应 DOC-04 Task 4.1 AgentPool,**但 API 不存在**
6. Env Vars → **完全新功能**,后端没有
7. Personalization → 对应 Batch 2 §A3-9 user_memories 表,但 Task 没定义
8. Harness Config → 对应 DOC-03 Task 3.6

**质量优先下的决定**:

有两种做法:
- **A**. UI design 作为未来 Roadmap,Phase 1 只做后端已有 API 对应的模块(1, 3, 8)
- **B**. 为缺失的后端 API 补 Task,确保前端全功能可用

用户明确说 "我要的是最终的完整应用,不是 demo",Phase 1 完整交付 —— 所以选 **B**。改写阶段必须:
- DOC-09 新增 Task 9.4: Slash Commands API + Sub Agents API + Env Vars API
- DOC-05 新增 Task 5.8: Personalization(User Memory)API
- 这些后端 Task 的优先级写进 review-master.md

#### AUI-3. 移动端"可用但不优化"的尺度

UI design §15:
> "策略:可用但不优化"

具体的降级清单:
```
桌面端独有,移动端隐藏:
- Agent Panel(合并到底部 tab sheet)
- 侧边栏(改为抽屉)

桌面端完整,移动端简化:
- TaskComposer: 去掉附件/模式选择器,保留输入 + 发送
- Capabilities Platform: 改为全屏模态页(非左右布局)
```

**用户要求的是**"**桌面端(1280x800)+ 移动端(375x812)每个按钮每个流程走一遍**",这和"移动端不优化"有矛盾。

**实际尺度**(质量优先下):
- 不是 "移动端只看不能操作",而是 "移动端能完成所有核心功能,但复杂视觉可以简化"
- 核心功能(发消息、看回复、管理 Provider、绑定 IM、看用量、装 Skill、Admin 管理)移动端**必须能用**
- 视觉上允许降级(Agent Panel 合并、侧边栏改抽屉),但功能**不能砍**

改写阶段 UI design §15 需要扩展 "移动端降级清单" + "移动端功能必须清单",明确两者边界。

---

## Part B — 架构级审视

### B4-I. 前端三份文档的关系必须明示 (B4-2)

DOC-10 / DOC-11 / UI design spec **现在是平行的三份**,没有主从关系。改写阶段必须在 DOC-10 开头加一段:

```markdown
## 文档关系

本文档(DOC-10)是前端**实现规范**,搭配以下两份文档工作:

1. **DOC-11 Frontend Features** — 功能实现规范(每个页面、每个功能的技术实现)
2. **2026-04-07 UI Design Spec** — **视觉真相源**,所有颜色 / 字体 / 布局 / 组件样式的 authoritative 定义

**优先级**:
- 视觉样式冲突时,以 UI Design Spec 为准
- 功能实现冲突时,以 DOC-11 为准
- 两者都未覆盖时,以 DOC-10(本文档)为准

Sonnet 4.6 实现前端时的阅读顺序:
1. 读 UI Design Spec 全文,理解视觉语言
2. 读 DOC-10(本文档)搭建基础
3. 读 DOC-11 按 Task 逐个实现功能
4. 实现时遇到视觉问题回查 UI Design Spec
```

### B4-II. Poco 424 文件 vs Prism 前端体积 < 10MB (B4-5)

**矛盾**: Poco 前端审计报告是 424 个文件、14 个功能模块。UI design 说 "Capabilities Platform 参考 Poco 68 文件架构完整保留"。但 DOC-00 说 "源码体积目标 < 10MB"。

**实际算账**:

Poco 源码 5MB (原版,用户原话)。Prism 如果做到和 Poco 相当的功能密度,源码应该也是 5-10MB 级。1.2GB 是 Prism v1 的 `node_modules` + `.next` 构建缓存,是依赖和构建产物,不是源码。

**修法**: 在 DOC-10 Task 10.1 明确区分:
- **源码体积**(frontend/src/) < 10MB — 这是现实的
- **node_modules**(不纳入 git 的依赖) 无硬限制
- **构建产物**(.next / standalone) < 150MB — 部署体积

而 Poco 424 文件不是"死胖子",是真实的功能模块分解。Prism 也会达到类似量级(可能更少,因为 Prism 架构更干净),但**文件数不是问题**,代码质量是。"文件数 < N 个"这种约束是错的,应该改为"**代码应该按功能和职责自然切分,不强行压缩**"。

### B4-III. SSE 流式事件的 Redis 直通对前端的影响

Batch 1 D3 决定了 Redis 直通方案 A。前端的 SSE 连接是:
```
/api/v1/sessions/{id}/stream?ticket=...
```

后端实现上,SSE 端点内部:
1. Redis SUBSCRIBE `sse:{session_id}`
2. 把收到的 Redis 消息转发到 SSE 响应流

前端看不到任何变化,**SSE 事件格式和以前一样**。这个设计好处 = 前后端解耦,坏处 = 后端转发加了一层复杂度。

**改写阶段验证**: DOC-10 的 SSE 客户端代码**和方案 A 完全兼容**,不用改。但后端 SSE 端点(DOC-07)的实现要按方案 A 重写。

### B4-IV. Agent Panel 的折叠状态持久化

UI design §6 的状态驱动逻辑:
```typescript
useEffect(() => {
  if (runStatus === 'running') setPanelOpen(true);
  // run 完成时不自动关闭,保持面板供用户查看
}, [runStatus]);
```

问题: 用户手动关闭面板后,下一个 Run 开始,面板又自动打开。有些用户就是不想看面板。

**修法**: 加个用户偏好:
```typescript
// localStorage: prism_agent_panel_mode = "auto" | "always_open" | "always_closed"

useEffect(() => {
  if (userPref === "auto" && runStatus === 'running' && !userManuallyClosed) {
    setPanelOpen(true);
  }
  if (userPref === "always_open") setPanelOpen(true);
  if (userPref === "always_closed") setPanelOpen(false);
}, [runStatus, userPref, userManuallyClosed]);
```

Settings 里可配置。

### B4-V. Playwright E2E 的质量保证

用户原话:
> "每个按钮每个流程走一遍,完全模拟人走一遍"

当前 DOC-11 每个 Task 都有 `npx playwright test xxx.spec.ts`,但**具体测试场景没列**。Sonnet 4.6 看这个指令会只测 happy path。

**改写阶段必须补**:每个 Task 的 Part B 里列出**完整的 E2E 测试场景清单**。比如 Task 11.1 对话界面:

```
Playwright E2E 场景清单(chat.spec.ts):

桌面端(1280x800) 必跑:
1. 新会话 → 发消息 → 看到 streaming 打字 → 完成
2. 发消息 → 点 stop → Run 被 cancel
3. 发消息触发工具调用 → tool card 展开 → 看到参数和结果
4. 发消息触发 guardrail → 看到 HarnessNotice 红色 badge
5. 触发 permission_ask → 弹窗出现 → 点 allow → 流程继续
6. 触发 permission_ask → 弹窗出现 → 点 deny → 看到 deny 反馈
7. 触发 permission_ask → 等待 5 分钟 → 超时提示
8. 网络断开 → 看到 offline 横幅 → 恢复 → 自动拉增量消息
9. 切换 Agent 类型(General → Research) → 新 Run 用新 Agent
10. 发起 Coordinator 任务 → Agent Panel 自动展开 → Steps tab 显示步骤

移动端(375x812) 额外:
11. 侧边栏抽屉展开关闭
12. Agent Panel 合并到底部 tab sheet
13. 触摸手势: 消息长按复制、滑动删除
14. TaskComposer 简化版可用

边界场景:
15. 连续发 50 条消息不卡
16. 超长消息(10000 字) 渲染
17. 中英混合 + emoji + 代码块 + 表格
18. markdown 渲染 edge case(嵌套列表、LaTeX)
```

---

## Part C — v3.1 新增 Task 评估

### C-1. Task 11.5 Skills 商店 & 插件创建 & Harness 配置 UI

**定位**: 对应 DOC-05 Task 5.5-5.7 的前端 + DOC-04 Task 4.5 PluginBuilder 的前端 + DOC-03 Task 3.6 的前端。

**Part A 已指出的问题**:
- A11-4 SkillCard 要展示 source + star + 更新时间
- A11-5 阶段感知通过 harness_event 子类型 + slot 状态
- Capabilities Platform(UI design §10)和 Task 11.5 有重叠,关系需要梳理

**质量优先最终建议**:

1. **Task 11.5 和 Capabilities Platform 的关系**:
   - `/skills` 和 `/plugins/create` 路由仍保留(作为独立入口)
   - `/capabilities` 下的 Skills / Plugins 子模块是这些页面的**聚合视图**,把分散的能力统一管理
   - 两者共享同一套组件(SkillCard / InstallDialog 等),不重复造轮子

2. **Harness 配置页按 Batch 2 §C1 简化**:
   - 只做"平台级规则查看(只读)" + "yaml 配置下载 / 上传" + "强制 reload"
   - 删除"可视化编辑 Guardrail 规则"功能(过度抽象,yaml 直接编辑更直接)
   - 删除"toggle middleware 运行时开关"(见 Batch 2 C1 建议)

3. **插件创建向导的实时预览**:
   - 左右布局保留
   - 右侧 "PluginStructureTree" 必须是**真实响应式的**——Agent 说"我会创建一个 financial-analysis skill",右侧就真的长出这个文件夹
   - 实现: 把 Agent 的工具调用监听到(create_file / file_write),更新 preview 状态

---

## 总结 & 对下一批的影响

### Batch 4 发现的问题量

- **实现级 (Part A)**: 17 项
- **架构级 (Part B)**: 5 项
- **UI design 与 DOC-10/11 一致性**: 贯穿多项

### 对 Batch 5 (Obs) 的影响

- **Prometheus 指标要包含前端指标**: SSE 连接数、重连次数、前端错误率(Sentry / 自建)
- **用户体验指标**: 首 token 延迟、平均响应时间、Cache 命中率 — 前端上报
- **前端错误上报通道**: 新增 `POST /api/v1/frontend-errors` 端点(简单版,不做 Sentry 但要有)

### 对改写阶段的关键影响

1. **DOC-10 几乎要完全重写**,Task 10.2 和 10.3 的 Part B 从"一段简述"扩展到"完整实现规范 + 状态机 + 边界处理 + E2E 场景"
2. **DOC-11 需要扩充**: Task 11.2 增加会话导出/分享/fork/归档/tag/多选;Task 11.3 扩充 IM 绑定 UX;Task 11.1 加 Agent Panel + coordinator plan 可视化;Task 11.4 扩充汇总卡片到 5 个(加 Cache 命中率);Task 11.5 和 Capabilities Platform 整合
3. **UI design spec 保持不变**,作为视觉真相源
4. **DOC-09 需要补 Task 9.4**: Slash Commands / Sub Agents / Env Vars API
5. **DOC-05 需要补 Task 5.8**: User Memory / Personalization API

---

> **下一步**: 进 Batch 5(Obs DOC-12)+ review-master.md
> **本 Batch 覆盖**: DOC-10 (9KB) + DOC-11 (25KB) + UI design (37KB) = ~71KB
