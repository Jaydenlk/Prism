# Prism v2 PRD 审计报告 — DOC-00 至 DOC-04

> **状态**: ✅ 已整合到 PRD v3.1 修订中（2026-04-05）
> **整合文档**: `docs/superpowers/specs/2026-04-05-prism-v2-prd-v3.1-revision-design.md`

> **文档编号**: DOC-AUDIT-00-04
> **日期**: 2026-04-04
> **性质**: 质量审计 — 记录 DOC-00~04 的架构审视发现，供全部文档完成后统一修补
> **审计方法**: 逐文档逐章节审读 + 跨文档一致性校验 + CC 架构映射验证
> **使用方式**: 全部 12 份文档完成后，对照此清单逐条执行修补，然后再做一轮完整的 brainstorming

---

## 1. 审计概要

### 1.1 整体评价

五份 PRD 的设计质量**很高**。CC 源码分析准确，Harness-Native 架构有差异化价值，双协议 Driver 务实，Task 拆分粒度合理（Part A 设计 + Part B 执行 prompt 的结构便于 Claude Code 直接执行）。核心架构方向正确，需要在实现细节处补全。

### 1.2 逐文档评分

| 文档 | 评分 | 核心评价 |
|------|------|---------|
| DOC-00 | 9/10 | 愿景清晰，原则有约束力，P7 原创亮点。缺测试规范。 |
| DOC-01 | 9/10 | 14 表精确，API 路由完整。sync/async 边界不明确。 |
| DOC-02 | 8.5/10 | 双协议 Driver 详尽。加密 key 独立性、cache 失效未处理。 |
| DOC-03 | 8/10 | Harness 核心全覆盖，但是最大风险单点。Task 间依赖不够灵活。 |
| DOC-04 | 8.5/10 | Agent 分工 + Fork 隔离设计精巧。Plan 解析脆弱，缺 fork 深度限制。 |

### 1.3 关键决策确认

以下讨论中确认的架构决策，在后续文档中应遵循：

| 决策 | 结论 | 讨论依据 |
|------|------|---------|
| PRD 范围策略 | 全量设计，实现分批交付 | 设计时考虑完整，实现时分期 |
| Executor DB 访问策略 | 混合模式：启动 sync 读，运行时 async callback 写 | Executor 运行时对 DB 无直接依赖 |
| 核心使用场景 | 混合场景：通用基底 + 垂类插件 | Plugin Ecosystem (DOC-05) 实现垂类特调 |
| IM Gateway 优先级 | 与 Web 端同优先级，Phase 2 同步开发 | DOC-08 的设计质量需要重点保证 |
| 测试策略 | 需要在 PRD 中增加测试规范 | pytest + mock + CI pipeline |

---

## 2. 逐文档改进项

### DOC-00: 愿景与设计原则

#### [DOC-00 §10] 缺少测试规范章节
- **问题**：§10 开发规范总纲包含 Git 工作流、命名规范、验收流程，但没有测试框架选型和策略
- **影响**：13+ 个 Task 的验证步骤全部是手动 curl + python -c 内联脚本，对 TAOR 主循环和 Harness 这种核心模块，缺乏自动化测试会导致后续改动回归风险极高
- **建议**：在 §10 增加 §10.8 测试规范，内容包括：
  - 测试框架：pytest + pytest-asyncio（Executor 的 async 代码）
  - Mock 策略：模型 API 调用用 `respx` 或 `pytest-httpx` mock，DB 用 test database + transaction rollback
  - 覆盖率要求：核心模块（TAOR 循环、Middleware Pipeline、Hook 系统）必须有单元测试
  - CI Pipeline：每个 Task 完成时必须 `pytest -x` 全过，作为验收流程的新增步骤
  - 集成测试：Docker 环境下的端到端测试框架（可用 pytest + docker-compose）
- **优先级**：**P0** — 必须修

#### [DOC-00 §10.4] 验收流程引用外部 Skill
- **问题**：步骤 7 引用 `Simplify skill`、步骤 8 引用 `PJR skill`，这些是 superpowers 插件的特定技能。换一个 Claude Code 实例或不用 superpowers 插件时，这两步就断了
- **影响**：验收流程的可移植性受损
- **建议**：将步骤 7 改为"代码质量审查（复用性、命名规范、效率）"，步骤 8 改为"lint + build + 逻辑验证"，在括号中注明推荐使用 Simplify 和 PJR skill（如可用）
- **优先级**：**P1** — 建议修

#### [DOC-00 §10.5] Skill 加载规则的外部依赖
- **问题**：§10.5 表格中 `Simplify`、`PJR`、`frontend-design`、`uiuxpromax` 都是外部 Skill，不一定在所有开发环境中可用
- **影响**：同上
- **建议**：将表格标题改为"推荐加载的 Skill"，并注明"如果 Skill 不可用，执行等效的手动审查步骤"
- **优先级**：**P1** — 建议修

---

### DOC-01: 系统架构

#### [DOC-01 §3/§9.1] sync/async 策略未明确
- **问题**：Executor 子进程的初始化阶段需要读 DB（sync），但 TAOR 循环是全 async 的。两者的边界在文档中没有明确说明
- **影响**：实现时可能在 async context 中调用 sync DB session，导致事件循环阻塞或 runtime error
- **建议**：在 §3.1 "CLI 子进程启动"流程的"AgentExecutor 初始化"步骤中，明确标注：
  ```
  AgentExecutor 初始化（sync 阶段，在 asyncio.run() 之前）
      ├─ 从 DB 读取 Run 配置（sync DB session）
      ├─ 从 DB 读取 Provider 信息（sync）
      ├─ 从 DB 读取 Plugin/MCP 配置（sync）
      └─ 关闭 DB session

  asyncio.run(main()) — 进入 async 阶段
      ├─ 初始化 Harness Runtime
      ├─ QueryEngine.run() — TAOR 主循环
      └─ 所有持久化操作通过 POST /internal/callbacks（async httpx）
  ```
  同时在 §9.1 "Backend ↔ CLI 子进程"中补充说明"Executor 运行时不直接访问 DB"
- **优先级**：**P0** — 必须修

#### [DOC-01 §4.2] harness_summary JSONB 缺少示例 schema
- **问题**：`runs.harness_summary` 描述为"Harness 运行摘要"，但没有定义 JSON 内部的 key 结构
- **影响**：DOC-03 实现时需要自行定义，可能与 DOC-12 的 Observability 需求不一致
- **建议**：在 `runs` 表定义后补充示例：
  ```json
  {
    "guardrail_triggers": 2,
    "hook_executions": 15,
    "permission_denials": 0,
    "compaction_triggers": 1,
    "compaction_tier_max": 1,
    "loop_detections": 0,
    "circuit_breaker_trips": 0,
    "middleware_errors": 0,
    "fork_count": 1,
    "total_tool_calls": 8
  }
  ```
- **优先级**：**P1** — 建议修

#### [DOC-01 §3.1] session_queue_items 的 promote 原子性
- **问题**：`SessionQueueManager.promote_next()` 被提及但没有说明原子性保障。如果 Backend 在 promote 过程中崩溃（标记了 promoted 但没启动 Run），队列消息会丢失
- **影响**：生产环境下的消息可靠性
- **建议**：在 §3 或 §4.2 中补充：
  - promote 操作使用 DB 事务保证原子性（update queue_item.status + create run + update session.blocking_run_id 在同一事务中）
  - Backend 启动时检查是否有 `status='promoted'` 但没有对应 `runs.status='running'` 的 queue_item，自动恢复
- **优先级**：**P1** — 建议修

#### [DOC-01 §11] 缺少推荐配置
- **问题**：只有 2C2G 的资源预算，没有推荐配置
- **影响**：用户可能用 2C2G 跑不起来（特别是 Coordinator 模式下）却不知道该升级
- **建议**：在 §2.2 的资源预算后面补充："2C2G 为最低配置（MAX_CONCURRENT_RUNS=1 时），推荐 4C4G（MAX_CONCURRENT_RUNS=2 + Coordinator 模式）"
- **优先级**：**P2** — 可选

---

### DOC-02: Model Adapter & Prompt Engine

#### [DOC-02 Task 2.2] Stream 解析缺少 JSON 容错
- **问题**：OpenAI Driver 中"工具调用参数是增量拼接的 JSON 字符串，需要在 tool_use_end 时 json.loads 完整字符串"，但没有处理 json.loads 失败的情况
- **影响**：某些国产 OpenAI 兼容 Provider（如硅基流动、Kimi）返回的 JSON 可能不规范（尾部多逗号、字符串未闭合等），导致工具调用整体失败
- **建议**：在 OpenAI Driver 的 stream 实现规范中补充：
  - json.loads 失败时，尝试使用 `json5`（宽松解析）或 `json_repair` 库修复
  - 修复也失败时，将原始字符串作为错误信息传回 StreamEvent(type="error")
  - 在 requirements.txt 中增加 `json-repair>=0.28.0` 作为可选依赖
- **优先级**：**P1** — 建议修

#### [DOC-02 Task 2.3] API Key 加密 key 独立性
- **问题**：API Key 使用"AES-256 加密，加密 key 从 JWT_SECRET 派生"。如果 JWT_SECRET 变更（比如安全事件后轮换），所有已存储的 API Key 都会解密失败
- **影响**：JWT_SECRET 轮换时需要同时重新加密所有 API Key，操作复杂且有数据丢失风险
- **建议**：
  - 在 `.env.example` 中增加独立的 `ENCRYPTION_KEY` 环境变量
  - `provider_service.py` 使用 `ENCRYPTION_KEY` 而非 `JWT_SECRET` 派生加密 key
  - 在 DOC-00 §10 的 `.env.example` 中同步更新
- **优先级**：**P0** — 必须修

#### [DOC-02 Task 2.4] PromptAssembler 静态缓存与工具列表变更
- **问题**：`tool_grammar_section(tools)` 被归为"静态 section"并缓存，但工具列表在 MCP Server 热加载/卸载时会变化。如果工具列表变了，static cache 不会失效
- **影响**：用户安装/卸载 MCP Server 后，Agent 的工具列表不更新（直到新 Session）
- **建议**：在 `PromptAssembler.build()` 中增加工具列表 hash 校验：
  ```python
  def build(self, **dynamic_kwargs) -> str:
      current_tools_hash = hash(tuple(t.name for t in self._tools))
      if self._static_cache is None or self._tools_hash != current_tools_hash:
          self._static_cache = self._build_static()
          self._tools_hash = current_tools_hash
      ...
  ```
- **优先级**：**P1** — 建议修

#### [DOC-02 Task 2.4] Token 估算精度
- **问题**：`1 token ≈ 4 英文字符 ≈ 1.5 中文字符` 是粗略估算，中英混合场景误差可达 20-30%
- **影响**：上下文预算判断可能提前或延迟触发 compaction
- **建议**：在 `ContextBudgetManager` 中留一个 `TokenEstimator` 接口：
  - Phase 1 使用字符数估算（当前方案）
  - Phase 2 可选接入 tiktoken（`tiktoken.encoding_for_model(model)`）做精确计算
  - 建议在 DOC-02 中标注此接口预留，并在 DOC-12 中规划接入
- **优先级**：**P2** — 可选

---

### DOC-03: Agent Runtime & Harness Core

#### [DOC-03 整体] 最大风险单点
- **问题**：5 个 Task 覆盖了 TAOR 主循环、Middleware Pipeline、Hook System、Permission Engine、Guardrails Engine、Feedback Loop、4 级 Compaction、6 层 Memory——这是整个 Agent 运行时的全部核心逻辑
- **影响**：任何一个 Task 延期或设计返工，都会阻塞 DOC-04 和所有后续文档
- **建议**：
  - 在文档开头增加"Task 间最小可行依赖"章节：
    - Task 3.1（TAOR 主循环）可以用 **stub middleware**（空 pipeline，直通）跑通，不依赖 3.2~3.4
    - Task 3.2（Middleware Pipeline）可以只实现 Pipeline 框架 + 1-2 个 middleware（如 LoopDetection + Observability），其他 middleware 逐步补充
    - Task 3.3（Hook System）可以先实现 command handler，http/prompt/agent handler 后补
    - Task 3.5（Compaction + Memory）可以先实现 Tier 0-1，Tier 2-3 后补
  - 这样即使某个 Task 的复杂功能没做完，主循环依然可以向后推进
- **优先级**：**P0** — 必须修

#### [DOC-03 Task 3.3] Hook 系统 21 事件过多
- **问题**：21 种生命周期事件在 Phase 1 不会全部用到。定义了但没有消费者的事件是死代码
- **影响**：实现和测试工作量增大，但收益为零（没有外部插件使用）
- **建议**：将 21 个事件分为两组：

  **Phase 1 必须（8 个）**：
  - SessionStart, SessionEnd
  - PreToolUse, PostToolUse, PostToolUseFailure
  - SubAgentStart, SubAgentStop
  - Notification

  **Phase 2 扩展（13 个）**：
  - Compact, PermissionRequest
  - TeammateIdle
  - TaskCreated, TaskCompleted
  - CwdChanged, ConfigChanged
  - 以及其他场景发现需要的事件

  Phase 1 实现事件分发框架 + 8 个必须事件，其他事件在框架中预留 enum 定义但不实现触发逻辑
- **优先级**：**P1** — 建议修

#### [DOC-03 Task 3.5] 6 层 Memory 复杂度
- **问题**：6 层 memory（project → user → session → auto → skill → team）全量实现的工作量和测试量巨大
- **影响**：延期风险
- **建议**：Phase 1 先实现 2 层：
  - **session memory**：单会话内的历史上下文管理（TAOR 循环核心依赖）
  - **user memory**：跨会话的用户偏好/记忆（对标 CC 的 auto memory）
  - 其他 4 层留 interface 定义 + 空实现，Phase 2 按需激活
- **优先级**：**P1** — 建议修

#### [DOC-03 §Guardrails] AI 分类兜底缺少规划
- **问题**：DOC-00 §4.3 提到"快速检查优先，AI 分类兜底"——用 LLM 判断不确定场景的权限。但 DOC-03 中没有规划这个 AI 分类的具体实现
- **影响**：GuardrailsEngine 的设计可能缺少 AI 分类接口
- **建议**：在 DOC-03 的 GuardrailsEngine 设计中预留 `AIClassifier` 接口：
  - Phase 1：只用确定性规则（正则/关键词/schema 校验），AI 分类返回 `UNKNOWN` 时默认放行
  - Phase 2：接入轻量模型（Haiku 级别）做分类，延迟预算 < 2s
  - 需要在 GuardrailsEngine 的 `evaluate()` 方法中增加 `classifier: Optional[AIClassifier] = None` 参数
- **优先级**：**P2** — 可选

---

### DOC-04: Agent Orchestration

#### [DOC-04 Task 4.2] 缺少 Fork 深度限制
- **问题**：当前设计中 Coordinator fork Planner，Planner 执行时可能通过工具又 fork Research——没有 fork 深度限制
- **影响**：恶意或错误的 prompt 可能触发无限嵌套 fork，耗尽内存
- **建议**：
  - 在 `ForkManager.__init__()` 中增加 `max_fork_depth: int = 2` 参数
  - 每次 fork 时传递 `current_depth + 1`
  - 达到限制时返回 `ForkResult(success=False, error="Fork depth limit reached")`
  - 在 DOC-04 Task 4.2 的"实现规范"中补充此限制
- **优先级**：**P0** — 必须修

#### [DOC-04 Task 4.3] Plan.parse_from_text() 解析可靠性
- **问题**：从 Planner Agent 的自然语言输出中解析结构化 Plan 对象。LLM 输出格式不稳定是常见问题
- **影响**：Plan 解析失败率可能很高，直接影响 Coordinator 模式的可用性
- **建议**：增加 retry + 结构化输出策略：
  1. 首次尝试 JSON 解析（Planner 的 output_format 要求 JSON）
  2. JSON 解析失败时，尝试 Markdown 列表解析（回退）
  3. 两种都失败时，将 Planner 输出 + 格式要求重新发给模型，要求返回严格 JSON（retry，最多 1 次）
  4. retry 也失败时，回退到单步 Plan
  5. 考虑对支持 structured output（如 Anthropic 的 tool_use 强制输出）的 Provider，用 tool_use 而非自然语言来获取结构化 Plan
- **优先级**：**P1** — 建议修

#### [DOC-04 Task 4.4] TaskRouter 关键词匹配的局限性
- **问题**：`"帮我搜索"` 匹配到 research agent，但 `"帮我搜索一下代码里的 bug"` 时应该用 general agent。关键词匹配无法区分上下文语义
- **影响**：路由误判率在实际使用中可能较高
- **建议**：
  - 在 DOC-04 中明确承认此局限性
  - 增加"路由覆盖"机制：用户可以在会话配置中显式指定 agent_type，覆盖自动路由
  - 在 DOC-12 的 Observability 中增加路由决策准确率的追踪指标
  - 标注 Phase 2 升级路径：关键词匹配 → LLM 单次分类（Haiku 级别，延迟 < 500ms）
- **优先级**：**P2** — 可选

---

## 3. 跨文档问题

### 3.1 测试策略（影响全部文档）

**现状**：每个 Task 的验证步骤都是手动执行。

**建议**：
- 在 DOC-00 §10 增加 §10.8 测试规范（见 §2 DOC-00 部分的详细建议）
- 每个 Task 的 Part B 验证步骤增加 pytest 自动化测试（不替换手动验证，作为补充）
- DOC-02~04 的每个 Task 完成后，对应的 `tests/` 目录下应有基础单元测试

### 3.2 sync/async 边界（影响 DOC-01, DOC-02, DOC-03, DOC-07）

**现状**：Backend 用 sync DB，Executor 全 async，边界不明确。

**确认的策略**：
- Executor 启动时 sync 读 DB（在 asyncio.run 之前）
- Executor 运行时所有持久化操作走 async callback HTTP
- Backend API 层用 sync DB session（FastAPI 的 Depends 注入）

**需要在以下文档中明确**：
- DOC-01 §3（子进程生命周期）— 标注 sync/async 分界
- DOC-02 Task 2.1（`__main__.py` 骨架）— 启动阶段标注 sync
- DOC-03 Task 3.1（TAOR 主循环）— 确认主循环中不调用 sync DB
- DOC-07（Session/Run/Task）— Backend callback 处理路径确认为 sync DB

### 3.3 IM 优先级一致性（影响 DOC-00, DOC-08）

**现状**：DOC-00 §2.5 说"IM 是核心功能（非 Phase 2 附属）"，但 DOC-08 被归入 Phase 2。

**确认的策略**：IM 和 Web 同步开发（Phase 2 同时做）。

**建议**：DOC-00 §11.3 的开发顺序图中，Phase 2 标注为：
```
Phase 2 — 后端功能模块 + IM（并行开发）
  DOC-06 → DOC-07 ──┐
                     ├→ DOC-09
  DOC-08 (IM) ──────┘
```
而非当前的纯串行 `DOC-06 → DOC-07 → DOC-08 → DOC-09`

---

## 4. 对 DOC-05~12 的影响提示

以下提示供撰写后续文档时参考：

| 文档 | 需要注意的审计发现 |
|------|------------------|
| DOC-05 Plugin Ecosystem | PromptAssembler 的工具列表 cache 失效问题（MCP 热加载场景）；Hook 系统的 Phase 分组（只触发 Phase 1 的 8 个事件） |
| DOC-06 Auth & User | 增加 `ENCRYPTION_KEY` 环境变量（与 `JWT_SECRET` 分离） |
| DOC-07 Session/Run/Task | promote 原子性保障；Backend callback 为 sync DB 处理路径；harness_summary 的 JSONB schema 定义 |
| DOC-08 IM Gateway | 与 Web 端同优先级设计；三平台共用消息路由和 session 管理抽象层 |
| DOC-09 MCP/Provider/Admin | Provider 管理与 DOC-02 Task 2.3 的 ProviderManager 的职责分界 |
| DOC-10 Frontend Foundation | SSE 事件需处理 `harness_event` 类型（前端展示 Harness 治理动态） |
| DOC-11 Frontend Features | 用量仪表盘的数据来源依赖 runs.input_tokens/output_tokens/cost_usd |
| DOC-12 Observability & Entropy | 内存用量监控（2C2G 约束）；路由决策准确率追踪；TokenEstimator 接口（精确计算）；harness_summary 消费与展示 |

---

## 5. 改进项优先级汇总

### P0 — 必须修（4 项）

| # | 文档 | 问题 |
|---|------|------|
| 1 | DOC-00 §10 | 缺少测试规范章节 |
| 2 | DOC-01 §3/§9.1 | sync/async 策略未明确 |
| 3 | DOC-02 Task 2.3 | API Key 加密 key 应独立于 JWT_SECRET |
| 4 | DOC-04 Task 4.2 | 缺少 Fork 深度限制 (max_fork_depth) |

### P1 — 建议修（10 项）

| # | 文档 | 问题 |
|---|------|------|
| 5 | DOC-00 §10.4 | 验收流程引用外部 Skill |
| 6 | DOC-00 §10.5 | Skill 加载规则的外部依赖 |
| 7 | DOC-01 §4.2 | harness_summary JSONB 缺少示例 schema |
| 8 | DOC-01 §3.1 | session_queue_items promote 原子性 |
| 9 | DOC-02 Task 2.2 | Stream JSON 解析缺少容错 |
| 10 | DOC-02 Task 2.4 | PromptAssembler 工具列表 cache 失效 |
| 11 | DOC-03 整体 | Task 间最小可行依赖不明确 |
| 12 | DOC-03 Task 3.3 | Hook 21 事件应分 Phase 1/Phase 2 |
| 13 | DOC-03 Task 3.5 | 6 层 Memory 应先实现 2 层 |
| 14 | DOC-04 Task 4.3 | Plan.parse_from_text() 解析可靠性 |

### P2 — 可选（4 项）

| # | 文档 | 问题 |
|---|------|------|
| 15 | DOC-01 §11 | 缺少推荐配置（4C4G） |
| 16 | DOC-02 Task 2.4 | Token 估算精度（预留 tiktoken 接口） |
| 17 | DOC-03 Guardrails | AI 分类兜底缺少规划 |
| 18 | DOC-04 Task 4.4 | TaskRouter 关键词匹配局限性 |

---

> **使用说明**：本文档记录了 DOC-00~04 的审计发现。待全部 12 份文档完成后，对照 §5 的优先级汇总逐条修补（P0 必须修，P1 建议修，P2 按需）。修补完成后可再跑一轮 brainstorming 做最终审视。
> **最后更新**: 2026-04-04
