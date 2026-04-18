# Prism 棱镜 v2 — 愿景与设计原则 (DOC-00)

> **文档编号**: DOC-00  
> **版本**: 3.1（Harness-Native 融合版）  
> **日期**: 2026-04-02  
> **性质**: 全局纲领文档 — 所有后续文档的根，任何开发会话读完此文档即可理解项目的方向和底线  
> **触发事件**: Claude Code v2.1.88 源码泄露（2026-03-31），揭示了生产级 Agent Operating System 的完整架构范式；2026 年 Harness Engineering 成为 Agent 领域主流工程范式  
> **前序**: Prism v1（Session 1-19）验证了执行链路可行性，但架构维度不足以构建有竞争力的产品

---

## 目录

1. [为什么要完全重写](#1-为什么要完全重写)
2. [产品定位重定义](#2-产品定位重定义)
3. [从 Claude Code 学到什么](#3-从-claude-code-学到什么)
4. [Harness Engineering：从 CC 到 Prism 的范式升级](#4-harness-engineering从-cc-到-prism-的范式升级)
5. [Prism v2 架构哲学](#5-prism-v2-架构哲学)
6. [设计原则](#6-设计原则)
7. [四条铁律](#7-四条铁律)
8. [安全模型](#8-安全模型)
9. [模型厂商策略](#9-模型厂商策略)
10. [开发规范总纲](#10-开发规范总纲)
11. [文档体系与开发顺序](#11-文档体系与开发顺序)
12. [会话恢复协议](#12-会话恢复协议)

---

## 1. 为什么要完全重写

### 1.1 Prism v1 的根本问题

Prism v1 从 Lumen 重建，经历 19 个开发会话后跑通了基本链路。但它的核心问题不在 bug 数量，而在架构维度：

**它是一个"会调工具的聊天转发器"，而不是一个 Agent Operating System。**

具体表现：

- **Executor 依赖 claude_agent_sdk** — 等于把 Agent Runtime 的核心能力（主循环、工具调度、上下文管理）外包给了第三方 SDK。Prism 自己只做了"把用户消息传给 SDK，把 SDK 回调转成 SSE"这一层薄壳。任何 SDK 不支持的行为（Agent 专业化、Fork 隔离、Coordinator 模式）都无法实现。
- **Prompt 是静态文本** — 没有动态装配、没有 cache boundary、没有 session-specific guidance 注入。
- **工具调用是裸执行** — 没有 PreToolUse/PostToolUse hook pipeline，没有权限决策层，没有结果截断与摘要。
- **单一 Agent** — 所有任务（探索、规划、执行、验证）都由同一个 Agent 完成，行为发散不可控。
- **前端代码膨胀** — 从 Poco 5MB 源码 fork 后膨胀至 1.2GB（含 node_modules 和构建缓存），大量冗余依赖。
- **无 Harness 层** — 没有护栏引擎、没有反馈闭环、没有可观测性、没有熵管理。Agent 在 demo 场景跑通，在生产场景崩溃。

### 1.2 Claude Code 泄露带来的认知升级

2026-03-31 泄露的 51.2 万行 TypeScript 源码揭示了一个关键事实：

> Claude Code 的竞争力不来自某个 system prompt，而来自一整套把 Prompt Architecture、Tool Runtime Governance、Permission Model、Agent Orchestration、Skill Packaging、Plugin System、Hook Governance、MCP Integration、Context Hygiene 和 Product Engineering 统一起来的 Agent Operating System。

更重要的是，CC 源码的架构本质上就是一个 **Agent Harness**——用 Philipp Schmid 的类比：Model = CPU，Context Window = RAM，**Harness = 操作系统**，Agent = 应用程序。CC 是第一个大规模验证了 Harness Engineering 范式的消费级产品。

### 1.3 Harness Engineering 的行业共识（2026）

2026 年初，Harness Engineering 成为 Agent 领域的主流工程范式：

- **OpenAI Codex 团队**用 Harness 驱动 Agent 写了 100 万行生产代码，零行人工手写
- **LangChain** 只改 Harness 不换模型，benchmark 从 52.8% 跳到 66.5%
- **Vercel** 砍掉 80% 的工具（Harness 层的减法优化），Agent 反而更快更准
- **Stripe Minions** 通过 Harness 实现每周 1300 个 AI PR
- **Martin Fowler** 在 ThoughtWorks 博客正式定义了 Harness Engineering

核心共识：**模型是商品，Harness 是护城河。** 更好的模型让 Harness 更重要，而不是更不重要。

### 1.4 重写范围

**完全重写。前端从零搭建，后端从零设计，Agent Runtime 自研，Harness 层原生内建。**

不从 v1 迁移代码，不做向后兼容。v1 中经过验证的业务逻辑（金融 MCP、合规 Hook、认证流程）可以作为参考，但必须按 v2 架构重新实现。

---

## 2. 产品定位重定义

### 2.1 一句话定位

> **Prism 是一个自托管的 Agent Operating System：通过 Harness 级别的护栏治理、模块化 Prompt 装配、可治理的工具执行 Pipeline、专业化的多 Agent 编排、热插拔的插件生态和多渠道 IM 接入，将通用大模型转化为可靠、可控、可扩展的 AI 协作者——无论用户在 Web 端、飞书、企业微信还是 Telegram 中发起对话。**

### 2.2 定位变迁

| 维度 | Prism v1 | Prism v2 |
|------|----------|----------|
| 本质 | 带插件的聊天转发器 | Agent Operating System + Harness |
| Agent Runtime | 外包给 claude_agent_sdk | 自研 TAOR 主循环 |
| Harness 层 | 无 | 原生内建（Middleware Pipeline + Guardrails + Feedback Loop + Observability） |
| Prompt 管理 | 静态文本 | 动态装配引擎，cache boundary 分层 |
| 工具执行 | SDK 直连 | 声明式定义 + Hook Pipeline + 权限决策 |
| Agent 模式 | 单一通用 Agent | 专业化分工（Explore/Plan/Execute/Verify） |
| 模型支持 | 仅 MiniMax（Anthropic 兼容） | 双协议适配（Anthropic + OpenAI 格式） |
| 上下文管理 | 无策略 | 4 级 Compaction Pipeline + Fork 隔离 + 结果截断 |
| 插件深度 | 配置级 MCP + 简单 Hook | Skill 三级加载 + 21 事件 Hook 治理 + MCP 行为注入 |
| 可观测性 | 无 | Tracing Pipeline + Token/Cost 追踪 + Entropy Detection |
| IM 接入 | 设计但未实现 | 飞书 + 企业微信 + Telegram，统一 IM Gateway |
| Provider 管理 | 单一模型硬编码 | 多 Provider 预设 + 故障转移 + 用量追踪 |

### 2.3 竞品对比

| 维度 | Prism v2 | Poco | Manus | Claude Code |
|------|----------|------|-------|-------------|
| 部署方式 | 自托管 Docker Compose | SaaS/Supabase 依赖 | SaaS 云端 | 本地 CLI |
| Agent Runtime | 自研，双协议 | claude_agent_sdk 封装 | 自研 | 自研 |
| Harness 层 | 原生 Harness（Guardrails + Feedback + Observability） | 无 | 部分（内置护栏） | 完整 Harness |
| 模型厂商 | 任意（Anthropic/OpenAI 兼容） | 仅 Anthropic 兼容 | 自有模型 | 仅 Claude |
| 插件系统 | Skill + Hook + MCP | 无 | Skills（三级加载） | Skill + Plugin + Hook + MCP |
| 多 Agent | Coordinator-Workers + Fork | 无 | Planner + Executor | Coordinator + Fork + Swarm |
| 数据主权 | 完全本地 | Supabase 云端 | Manus 云端 | 本地 |
| Web UI | 有（Claude 风格） | 有 | 有 | 无（CLI） |
| 开源 | 完全开源 | 部分 | 闭源 | 已泄露非正式开源 |
| 硬件要求 | 2C2G VPS 可运行 | 云端 | 云端 | 本地开发机 |
| IM 接入 | 飞书/企业微信/Telegram | 无 | 无 | 无（CLI only） |
| 熵管理 | Detection + Alert + 人工触发清理 | 无 | 无 | 无显式机制 |

### 2.4 目标用户

**主要用户 — "主权开发者"**：有技术背景，需要 AI Agent 能力但不愿将数据交给 SaaS。自己部署，通过邀请码分享给 5-20 人的信任圈。

**次要用户 — "受邀成员"**：通过邀请码获得访问权，只使用 Web 聊天界面或 IM 渠道，不接触服务器和配置。

### 2.5 双入口架构：Web + IM

Prism 的用户触达不限于 Web 界面。IM 集成是核心功能（非 Phase 2 附属），目标是让 AI 协作者出现在用户已经在使用的地方。

**支持的 IM 渠道（Phase 1）**：

| 平台 | 接入方式 | 是否需要公网 IP | 参考实现 |
|------|---------|----------------|---------|
| 飞书 (Feishu/Lark) | WebSocket 长连接 | 否 | OpenClaw 官方飞书插件 |
| 企业微信 (WeCom) | 自建应用（可桥接普通微信） | 是（Webhook 回调） | openclaw-china/wecom-app |
| Telegram | Bot API (Long Polling / Webhook) | 可选 | OpenClaw 原生支持 |

**架构原则**：

```
用户消息 → IM 平台
    ↓
Prism IM Gateway（消息路由 + 格式标准化）
    ↓
POST /api/v1/tasks（等同于 Web 端提交任务）
    ↓
Harness Runtime → Agent Runtime 执行
    ↓
结果通过 IM 渠道回传
```

Web 端和 IM 端共享同一个 Session、同一个 Harness Runtime、同一套插件生态。IM 端是轻量入口（文本交互为主），Web 端功能更丰富（工具卡片、文件预览、MCP 配置等）。用户通过配对码将 IM 账号绑定到 Prism 账号，实现跨渠道身份统一。

### 2.6 参考产品：cc-switch

[cc-switch](https://github.com/farion1231/cc-switch) 是一个跨平台桌面工具，统一管理 Claude Code、Codex、Gemini CLI、OpenCode、OpenClaw 五个 CLI 工具的 Provider 配置。以下设计对 Prism 有直接参考价值：

- **50+ Provider 预设** — 用户不需要手动查找 base_url，选择厂商即可一键配置
- **自动故障转移 + 熔断器** — 主 Provider 失败时自动切换到备用 Provider，并对不健康的 Provider 做熔断保护
- **用量仪表盘** — 跨 Provider 追踪 Token 消耗、请求数、成本趋势
- **统一 MCP/Skills 管理** — 一个面板管理所有工具的 MCP 和 Skills，双向同步

---

## 3. 从 Claude Code 学到什么

基于泄露源码分析（PDF 深度研究报告 + Max For AI + huangserva + billtheinvestor 等多方解析），提炼以下 Prism v2 必须吸收的核心设计理念：

### 3.1 Prompt 不是文本，是 Runtime Assembly

CC 的 `getSystemPrompt()` 不是返回一个字符串，而是一个编排器：

- **静态前缀**（identity、system rules、task philosophy、tool usage grammar）—— 高度稳定，适合缓存
- **动态后缀**（session guidance、memory、env info、MCP instructions、language）—— 按会话条件注入
- **SYSTEM_PROMPT_DYNAMIC_BOUNDARY** 标记严格区分两者

**Prism v2 映射**：实现 `PromptAssembler` 类，管理静态/动态分段，按厂商能力决定缓存策略。

### 3.2 Tool 不是裸调，是治理 Pipeline

CC 的工具执行链路：找工具 → 解析 MCP 元数据 → input schema 校验 → validateInput → PreToolUse hooks → 权限决策 → 执行 → PostToolUse hooks → 结构化输出 → 失败则 PostToolUseFailure hooks。

Hook 不只能记日志，还能：改写输入（`updatedInput`）、决定权限（`allow/ask/deny`）、阻断继续（`preventContinuation`）、追加上下文（`additionalContext`）。

**Prism v2 映射**：实现 `ToolExecutionPipeline` 类，每次工具调用走完整 pipeline，Hook 具备控制流参与能力。

### 3.3 Agent 不是万能 Worker，是专业化分工

CC 内建至少 6 种 Agent：

- **General Purpose** — 通用任务
- **Explore** — 纯只读代码探索，被故意裁成 read-only specialist
- **Plan** — 纯规划不执行，输出 step-by-step plan + critical files
- **Verification** — 对抗性验证者，目标是"try to break it"，强制跑 build/test/lint/adversarial probes
- **Claude Code Guide** — 使用引导
- **Statusline Setup** — 状态栏配置

**Prism v2 映射**：至少实现 General、Research（对应 Explore，适配非代码场景）、Planner、Verifier 四种专业化 Agent。

### 3.4 Fork 不是"再开一个 Agent"，是上下文隔离 + 缓存共享

CC 的 Fork 机制核心价值：

- 子 Agent 继承父对话的 Prompt Cache（byte-identical prefix），不额外烧 token
- 子 Agent 的探索动作、垃圾上下文完全隔离在自己的上下文中
- 执行完毕只传回结论（synthesis），不污染主上下文

**Prism v2 映射**：实现 `ForkContext` 机制，Fork Agent 共享 system prompt 和历史上下文的引用，但拥有独立的 working context。结果通过 `NodeResult` 结构回传。

### 3.5 Coordinator-Workers 是复杂任务的解法

CC 的 Coordinator Mode：

- Coordinator 被剥夺直接操作能力，只保留 Agent（派生子代理）、SendMessage、TaskStop
- 工作流：Research → Synthesis → Implementation → Verification
- Workers 携带具体工具被派生出来

**Prism v2 映射**：对于简单任务走单 Agent 直接执行；对于复杂任务（Planner 判定需要多步骤），自动切换 Coordinator-Workers 模式，将任务分解为多个 Step，逐步执行。这就是"分布式执行——将大任务拆成好几个步骤一步一步来"。

### 3.6 "好行为"要制度化，不能靠模型即兴发挥

CC 的 `getSimpleDoingTasksSection()` 把行为规范写进了 System Prompt：

- 不要加用户没要求的功能
- 不要过度抽象
- 不要瞎重构
- 先读代码再改代码
- 方法失败时先诊断再换策略
- 结果要如实汇报，不能假装测试过

**Prism v2 映射**：在 PromptAssembler 的静态前缀中内嵌行为规范模块，确保 Agent 行为一致性。不同 Agent 类型有不同的行为约束（Explore Agent 绝对只读，Planner Agent 只规划不执行）。

### 3.7 上下文是稀缺资源，要当预算管理

CC 大量设计围绕上下文优化：

- System Prompt 静动态边界
- Prompt Cache boundary
- Fork path 共享 cache
- Skill 按需注入
- 工具结果截断 + 摘要
- Function result clearing
- 4 级 Compaction Pipeline（micro-compact → auto-compact → session memory → reactive truncation）

**Prism v2 映射**：实现 `ContextBudgetManager`，追踪当前上下文 token 消耗，工具结果超过阈值自动截断并生成摘要，长对话自动压缩历史消息。对标 CC 的 4 级渐进式 compaction 策略。

---

## 4. Harness Engineering：从 CC 到 Prism 的范式升级

### 4.1 CC 已经是一个 Harness，但 Prism 需要更进一步

CC 源码本身就是一个完整的 Agent Harness。它通过 TAOR 循环、Hook 系统、权限模型、Compaction Pipeline、Sub-Agent 隔离等机制解决了 8 大 Agent 失败模式。但 CC 是一个**面向个人开发者的本地 CLI**，而 Prism 是一个**面向团队的自托管分布式平台**，需要额外解决：

- 跨节点的 Harness 状态同步
- 多用户场景下的护栏隔离
- 生产环境的熵漂移检测与治理
- 分布式任务调度中的 Harness 一致性

### 4.2 CC 失败模式与 Prism Harness 解法映射

| # | 失败模式 | CC 解法 | Prism v2 Harness 解法 | 所属 DOC |
|---|---|---|---|---|
| 1 | Runaway Loops（失控循环） | maxTurns + model-driven stop | maxTurns + Loop Detection Middleware + Circuit Breaker | DOC-03 |
| 2 | Context Collapse（上下文崩溃） | 4 级 compaction + sub-agent 隔离 | 4 级 Compaction Pipeline + Sub-Agent Context Isolation | DOC-03 |
| 3 | Permission Roulette（权限混乱） | 6 种权限模式 + 工具级 allow/deny/ask | 分层权限引擎（平台级 + 插件级）+ 风险路由 | DOC-03 |
| 4 | Amnesia（健忘） | 6 层 memory 系统 | 6 层 memory（project → user → session → auto → skill → team） | DOC-03 |
| 5 | Monolithic Context（单体上下文） | Sub-agent 隔离 TAOR + Agent Teams 并行 | Sub-Agent 隔离 + 分布式 Agent Teams | DOC-04 |
| 6 | Hard-Coded Behavior（硬编码行为） | 声明式扩展（Skills/Agents/Hooks/MCP/Plugins） | 声明式插件体系 + 垂类特调 | DOC-05 |
| 7 | Black Box（黑盒） | Hooks 在每个生命周期事件触发 | Observability Pipeline + 21 类生命周期 Hook | DOC-03 + DOC-06 |
| 8 | Single-Threaded（单线程） | Sub-agents + Agent Teams | 分布式 Worker Pool + Agent Teams + Worktree 隔离 | DOC-04 |
| 9 | Entropy Drift（熵漂移）⚡新增 | CC 无显式解法 | Entropy Detection + Alert + 人工触发清理 | DOC-06 |

> ⚡ #9 是 Prism v2 超越 CC 的差异化设计点。OpenAI Codex 团队曾每周花 20% 时间手动清理 AI slop，Prism 将这个过程系统化为检测 + 告警 + 人工触发。

### 4.3 Harness 核心子系统预览

以下子系统在 DOC-03（Agent Runtime & Harness Core）中详细设计：

**TAOR 主循环**（对标 CC 的 `query.ts` while(true) 循环）：
```
Think → Act → Observe → Repeat
1. Prefetch memory + skills (并行)
2. Middleware Pipeline 前处理
3. Prompt Assembly (static + dynamic + cache boundary)
4. API Call (streaming)
5. Tool Dispatch (权限检查 → 执行 → 结果)
6. Observe: 结果追加到 messages[]
7. Compaction Check (阈值触发 4 级策略)
8. Loop Detection Check
9. stop_reason == "end_turn" → 退出 / "tool_use" → 回到 Step 2
```

**Middleware Pipeline**（可插拔中间件链，每个中间件单一职责）：
```
Request → ContextEnrichmentMW → LoopDetectionMW → PermissionGateMW
        → RateLimitMW → [TAOR Core] → OutputValidationMW
        → FeedbackCaptureMW → ObservabilityMW → Response
```

**Hook System（21 类生命周期事件）**（对标 CC 的 Hook 体系，4 种 handler 类型）：

| 事件类别 | 事件 | 触发时机 |
|---|---|---|
| Session | SessionStart, SessionEnd, Compact | 会话生命周期 |
| Tool | PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest | 工具调用前后 |
| Agent | SubAgentStart, SubAgentStop, TeammateIdle | 子 Agent 生命周期 |
| Task | TaskCreated, TaskCompleted | 分布式任务生命周期 |
| System | Notification, CwdChanged, ConfigChanged | 系统事件 |

Handler 类型：`command`（shell 脚本）、`http`（webhook）、`prompt`（LLM 审查）、`agent`（sub-agent 审查）

权限决策协议对标 CC：exit 0 + JSON → 成功（解析 permissionDecision/updatedInput），exit 2 → 阻断（stderr 反馈给 Agent），其他 → 非阻断警告。

**Permission Engine（分层权限模型）**：
```
平台级护栏（全局生效，不可被插件覆盖）:
├── 破坏性操作拦截（DELETE/DROP/rm -rf 等）
├── 速率限制（工具调用频率 + token 消耗速率）
├── 敏感数据过滤（PII/API Key 检测）
└── Circuit Breaker（连续失败熔断）

插件级护栏（随插件加载/卸载）:
├── 垂类业务规则（如金融场景禁止未审批的交易操作）
├── 输出 schema 校验
└── 自定义审批流程
```

快速检查优先，AI 分类兜底——确定性规则检查（ms 级）先行，无法枚举的场景用 LLM 分类（秒级）兜底。

---

## 5. Prism v2 架构哲学

### 5.1 五层架构

对标 CC 源码的 5 层架构，Prism v2 从旧的 4 层升级为 5 层，新增 Harness Runtime 作为独立核心层：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Entrypoints (入口层)                               │
│  Web UI / REST API / SSE Stream / IM Gateway / SDK（未来）   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Orchestration (编排层)                              │
│  TaskScheduler / RunLifecycle / SessionQueueManager          │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Harness Runtime (Harness 运行时层) ⚡新增           │
│  TAOR Loop / Middleware Pipeline / Hook System (21 事件) /   │
│  Permission Engine / Guardrails Engine / Lifecycle Controller │
│  / Feedback Loop Engine / Loop Detection / Circuit Breaker   │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Agent & Engine Core (Agent 引擎层)                 │
│  QueryEngine / PromptAssembler / ToolExecutionPipeline /     │
│  AgentPool / ForkManager / ContextBudgetManager /            │
│  4-Tier Compaction / 6-Layer Memory / PluginHost             │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Infrastructure (基础设施层)                         │
│  AnthropicDriver / OpenAIDriver / ProviderManager /          │
│  Auth / Storage / Cache / Observability & Tracing            │
└─────────────────────────────────────────────────────────────┘
```

每一层只与相邻层通信，禁止跨层调用。Layer 3 Harness Runtime 是新增的核心层，包裹 Layer 4 的 Agent 引擎，提供治理、护栏和生命周期管理能力。

### 5.2 服务拓扑

```
Docker Compose
├── backend        (FastAPI — 包含 Orchestration + Harness Runtime + Agent Engine + Infra)
│   └── CLI 子进程  (Agent 执行，进程级隔离，任务结束即退出)
├── postgres       (PostgreSQL 16)
├── redis          (Redis 7 — SSE pub/sub + 缓存 + Harness 状态同步)
└── nginx          (反向代理 + 静态文件 + 前端 standalone)
```

四个服务，不多不少。Backend 是唯一的应用服务，Agent 执行通过 CLI 子进程在同一容器内运行。

### 5.3 关键设计决策摘要

| 决策 | 选择 | 理由 |
|------|------|------|
| 项目起点 | 全新文件夹，从零开始 | 不从 v1 迁移任何代码，避免历史债务 |
| Agent Runtime | 自研 TAOR 主循环 | 完全控制行为、不受 SDK 限制、可实现 CC 级别的编排能力 |
| Harness 层 | 原生内建于 Layer 3 | 不是插件或附加模块，是操作系统级的核心层 |
| 模型协议 | 双 Driver（Anthropic + OpenAI） | 覆盖市面上 95% 的模型厂商 |
| Provider 管理 | 内置预设 + 故障转移 + 用量追踪 | 参考 cc-switch，自托管用户需要成本可见性 |
| Executor 隔离 | CLI 子进程（非独立容器） | 消除冷启动延迟、简化拓扑、2C2G 友好 |
| IM 集成 | 飞书 + 企业微信 + Telegram | 覆盖国内企业（飞书）、个人微信桥接（企业微信）、海外（Telegram） |
| 前端构建 | 从零搭建（非 fork） | 控制体积、消除冗余、统一风格 |
| 前端风格 | Claude.ai 网页端视觉语言 | 低沉、准确、稳定的设计感 |
| ORM 模式 | SQLAlchemy 2.0 sync | 简单可控，避免 async ORM 的复杂性 |
| 数据库迁移 | 手写 Alembic Migration | 禁止 autogenerate，保证迁移质量 |
| Harness 架构 | Rippable（可撕裂） | 模型能力升级时，补偿性 middleware 可快速移除 |
| 熵管理 | 检测 + 告警 + 人工触发 | 半自动模式，避免过度自动化引入新风险 |

---

## 6. 设计原则

### P1: Agent OS + Harness，不是聊天转发器

Prism 的核心价值不在"把消息传给模型再传回来"，而在 Harness 治理、Prompt 装配、工具管控、Agent 编排、插件生态这五层能力的协同。每一行代码都要问：它是在增强 Agent OS 的能力，还是在做简单的 IO 转发？

### P2: 制度化优于即兴发挥

Agent 的行为稳定性不靠模型聪明，靠规则约束。所有的"好行为"都要写进 Prompt 和 Harness Runtime 规则中，不留给模型自由裁量。每次 Agent 犯错，修复方式不是"换个 prompt 试试"，而是"在 Harness 中新增一条永久性约束"。

### P3: 上下文是预算，不是免费空气

每一个注入 System Prompt 的 section、每一个工具调用的结果、每一条历史消息，都在消耗有限的上下文窗口。系统必须主动管理上下文预算：静态 section 缓存、工具结果截断摘要、长对话 4 级渐进式 compaction、Fork 隔离垃圾上下文。

### P4: 结果最简，不是过程最简

代码量不是目标，代码质量和运行正确性才是。宁可花更多时间设计和重构，也不打补丁。宁可破坏性更新，也不做向后兼容的累赘。

### P5: 配置驱动，不是硬编码

插件行为由配置（SKILL.md + Hook 脚本 + MCP config）控制，不由 Prism 核心代码控制。新增一个插件不应该需要修改 Prism 的任何一行核心代码。Harness 的护栏规则同样声明式配置。

### P6: 声明式优于命令式

工具通过 Schema 声明输入输出和权限边界，Agent 通过定义文件声明能力范围和行为约束，Guardrails 通过规则声明触发条件和处置动作。运行时读取声明并执行，而不是在代码中 if-else 分发。

### P7: Build to Delete（可撕裂架构）⚡新增

模型能力升级时，Harness 中"补偿模型不足"的逻辑要能快速移除，而不是变成技术债。每个 Middleware 都是独立模块，关掉一个不影响其他。如果需要解释某个 Middleware 为什么存在，要能回答"当模型足够强时，它可以被移除"。

---

## 7. 四条铁律

铁律不可妥协。不论任何功能需求、任何插件扩展、任何用户请求，以下四条铁律在系统中通过 Harness 多层强制执行。

### 铁律 1: 无投资建议

**内容**：系统不得生成任何可被解释为投资建议的内容。

**Harness 强制层级**：
- System Prompt 层 — 明确禁止生成投资建议（PromptAssembler 静态 compliance_section）
- Guardrails Engine — 平台级护栏规则 `GR-COMPLIANCE-001`，PostToolUse 阶段检测并拦截
- Hook 层 — `ComplianceHook` 在 PostToolUse 事件检测投资建议性内容
- API 层 — 触发拦截时写入审计日志

### 铁律 2: 数据溯源

**内容**：所有引用的数据必须标注来源。

**Harness 强制层级**：
- MCP Tool 层 — 每个数据工具的返回值自动附带 `source_label`
- Guardrails Engine — 平台级护栏规则 `GR-COMPLIANCE-002`，检测响应中的数字是否有溯源标注
- Hook 层 — `ComplianceHook` 在 PostToolUse 检测

### 铁律 3: AI 标识

**内容**：所有 Agent 生成的内容必须标注 AI 生成标识。

**Harness 强制层级**：
- Hook 层 — `ComplianceHook` 在 SessionEnd 事件的最终输出末尾自动追加 `[AI 生成内容 | Prism 棱镜]`
- Middleware — OutputValidationMW 确保标识存在

### 铁律 4: 数据隔离

**内容**：不同用户的数据严格隔离，不得跨用户访问。

**Harness 强制层级**：
- Repository 层 — 所有查询强制 `WHERE user_id = :current_user_id`
- Guardrails Engine — 平台级护栏规则 `GR-ISOLATION-001`，拦截跨用户数据访问
- Code Review — 审查 checklist 的强制检查项

---

## 8. 安全模型

### 8.1 Agent 执行隔离

Agent 任务通过 Backend 内部的 CLI 子进程执行：

- 每个任务分配独立工作目录 `/workspace/{run_id}/`
- 子进程以降权用户运行（非 root）
- 工作目录任务结束后可选保留或清理
- 子进程无法访问 Backend 的数据库连接和内存空间

### 8.2 网络隔离

子进程的网络访问限制为白名单：
- 模型 API 端点（用户配置的 base_url）
- 用户配置的 MCP Server 端点
- 禁止其他出站连接

### 8.3 工具权限（Harness 层治理）

所有工具调用通过 Harness 的 `ToolExecutionPipeline`：
- Input Schema 校验
- PreToolUse Hook 可拦截、改写、拒绝
- Permission Engine 风险路由：低风险自动放行，中风险 Hook 审查，高风险人工确认
- 高危操作（文件删除、网络请求、数据修改）需要 Hook 显式放行或用户确认
- PostToolUse Hook 验证输出合规性

### 8.4 认证与授权

- JWT access token（短期）+ refresh token（HttpOnly cookie）
- 邀请码控制注册入口
- 角色系统：`admin` / `user`
- 所有 API 端点强制认证（除 /health 和 /auth/*）

---

## 9. 模型厂商策略

### 9.1 双协议架构

Prism v2 支持两种 API 协议，覆盖市面上几乎所有主流模型厂商：

**Anthropic Messages API 协议**：
- 适用厂商：Anthropic (Claude)、MiniMax（兼容模式）
- 特性：`content` 数组含 `text` / `tool_use` / `tool_result` block，streaming 通过 `message_start` / `content_block_delta` / `message_stop`
- 支持 Prompt Cache（前缀匹配）的厂商可启用 cache boundary 优化

**OpenAI Chat Completions API 协议**：
- 适用厂商：OpenAI (GPT)、DeepSeek、Kimi (Moonshot)、Qwen (通义)、Gemini (Google)、以及其他 OpenAI 兼容服务
- 特性：`messages` 数组，`tool_calls` 独立字段，streaming 通过 `choices[0].delta`

### 9.2 用户配置

用户在 Prism 中配置模型时提供三项信息：

```
protocol: "anthropic" | "openai"
base_url: "https://api.minimaxi.com/anthropic"  # 或任何兼容端点
api_key: "sk-..."
```

Prism 内部使用统一的 `PrismMessage` 格式，两个 Driver（`AnthropicDriver` / `OpenAIDriver`）各自负责与厂商 API 的双向格式转换。

**内置 Provider 预设**（参考 cc-switch）：

| 厂商 | 协议 | 预设 base_url |
|------|------|--------------|
| Anthropic | anthropic | `https://api.anthropic.com` |
| OpenAI | openai | `https://api.openai.com/v1` |
| DeepSeek | openai | `https://api.deepseek.com` |
| MiniMax | anthropic | `https://api.minimaxi.com/anthropic` |
| Kimi (Moonshot) | openai | `https://api.moonshot.cn/v1` |
| Qwen (通义) | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Gemini | openai | `https://generativelanguage.googleapis.com/v1beta/openai` |
| 硅基流动 | openai | `https://api.siliconflow.cn/v1` |

用户也可以自定义任意兼容端点。

### 9.3 多 Provider 与故障转移

用户可配置多个 Provider（主 + 备用）。系统行为：

- 默认使用主 Provider 发送请求
- 主 Provider 连续失败 N 次（可配置）后，自动切换到备用 Provider
- 不健康的 Provider 进入熔断状态，一段时间后自动探测恢复
- 切换事件记录审计日志

### 9.4 用量追踪

每次模型调用记录：Provider、模型名、input_tokens、output_tokens、成本（基于用户配置的单价）。提供按日/周/月的用量统计 API，前端展示用量仪表盘。

### 9.5 能力分级

不同厂商 API 的能力不同，Prism 按能力分级适配：

| 能力 | 支持时的行为 | 不支持时的降级 |
|------|------------|--------------|
| Prompt Cache | 启用 cache boundary，静态前缀最大化缓存命中 | 禁用 boundary 标记，正常发送完整 prompt |
| Streaming tool_use | 流式返回工具调用参数 | 等待完整响应后解析工具调用 |
| Extended thinking | 启用思考过程可见 | 跳过，正常对话 |
| Vision（图片输入） | 支持图片 message | 忽略图片，仅处理文本 |

---

## 10. 开发规范总纲

### 10.1 代码原则

1. **单一职责** — 每个服务、类、方法只负责一个明确的职责域
2. **最简代码** — 不做向后兼容，宁愿破坏性更新也要保持代码最简，删除所有冗余
3. **类型严格** — TypeScript 不使用 `any`，Python 使用完整的 type hints，编译/类型检查错误必须立即修复
4. **KISS** — 保持简单直接，如果需要解释就是太复杂了
5. **文档置信度** — 绝不基于推测写代码，涉及关键功能时文档置信度不高必须停止并要求准确资料
6. **禁止打补丁** — 所有修改必须深度融入代码逻辑，通过重构或调整现有逻辑的方式实现，严禁不从根源解决问题

### 10.2 命名规范

| 类别 | 规范 | 示例 |
|------|------|------|
| 数据库表名 | snake_case 复数 | `agent_sessions`, `agent_runs` |
| Python 类 | PascalCase | `SessionService`, `ToolExecutionPipeline` |
| Python 函数/变量 | snake_case | `enqueue_task()`, `run_id` |
| TypeScript 组件 | PascalCase | `ChatMessage`, `SessionList` |
| TypeScript 函数/变量 | camelCase | `fetchMessages()`, `sessionId` |
| API 路径 | kebab-case | `/api/v1/mcp-servers` |
| 主键 | UUIDv7 | 时间有序，可排序，全局唯一 |
| API 响应 | `ApiResponse<T>` 统一封装 | `{ data: T, error?: { code, message } }` |

### 10.3 Git 工作流

- 所有开发在 **Worktree** 中执行
- 分支命名：`feat/{module}-{description}` 或 `fix/{module}-{description}`
- 完成后合并回 `develop` 分支（git merge to dev）
- 每次合并前必须通过完整的 lint + build + E2E 测试

### 10.4 Task 验收流程

每个 Task 的完整验收：

```
1. 编译通过 — Python: mypy/pyright 类型检查，TypeScript: npx tsc --noEmit 零错误
2. 后端非 AI 接口 — pytest: 正常结果 + 异常结果 + 数据隔离测试
3. 后端 AI 接口 — pytest: 复杂场景决策能力测试 + 执行能力测试 + 边界场景测试
4. 前端 — Playwright E2E: 桌面(1280x800) + 移动(375x812)，正常流程 + 边界场景
5. 文档更新 — PROGRESS.md 状态更新、DECISIONS.md 新增 ADR（如有技术决策）
6. 代码规范 — UUIDv7、ApiResponse<T>、丰富注释、无魔法数字
7. 代码质量审查 — 复用性、命名规范、效率（推荐使用 Simplify skill 如可用）
8. lint + build + 逻辑验证（推荐使用 PJR skill 如可用）
9. 合并 — git merge to dev 流程
```

### 10.5 Skill 加载规则

以下 Skill 在对应场景下**推荐加载**。如果 Skill 不可用，执行等效的手动审查步骤：

| 场景 | 推荐加载的 Skill |
|------|-----------------|
| 所有开发任务 | `using-superpowers` |
| 代码审查阶段 | `Simplify` |
| lint/build/合并阶段 | `PJR` |
| 涉及前端开发 | `frontend-design` + `uiuxpromax` |

### 10.6 数据库迁移规范

**开发环境**：SQLAlchemy `create_all()` 或 Alembic `upgrade head` 自动同步，快速迭代。

**生产环境**：

- 所有迁移由 AI（Claude Code）手写，禁止 `alembic revision --autogenerate`
- 每个迁移文件必须有对应的 `upgrade()` 和 `downgrade()`
- 原子化操作 — 拆分为多个小的独立迁移
- 文件命名：`{sequence}_{description}.py`（如 `001_create_users_table.py`）
- 禁止直接操作生产数据库表结构（无论 SQL 命令还是图形化工具）

### 10.7 前端开发规范

- 从 `create-next-app` 干净起步，TypeScript strict 模式
- UI 组件库：shadcn/ui（可定制，无锁定）
- CSS：Tailwind CSS
- 状态管理：TanStack React Query v5（服务端状态）+ Zustand（少量客户端状态）
- 视觉风格：Claude.ai 网页端 — 衬线标题字体、深灰/暖白配色、大量留白、简洁对话区
- 源码体积目标：< 10MB（不含 node_modules）
- 构建产物（standalone）体积目标：< 150MB

### 10.8 测试规范

**测试框架选型**：

| 层 | 框架 | 用途 |
|----|------|------|
| 后端单元测试 | pytest + pytest-asyncio | Service 层、核心模块 |
| 后端 Mock | respx（HTTP mock）+ pytest-httpx | 模型 API 调用 mock |
| 后端 DB 测试 | test database + transaction rollback | 每个测试用例自动回滚 |
| 前端 E2E | Playwright | 桌面(1280x800) + 移动(375x812) 双视口 |
| CI | pytest -x + npx playwright test | 每个 Task 完成时必须全过 |

**后端测试 — 非 AI 接口**：

所有 CRUD、Auth、Provider、MCP、IM 等非 AI 接口必须覆盖：

- **正常结果测试**：标准输入 → 预期输出，验证 HTTP 状态码 + 响应体结构 + 数据持久化
- **异常结果测试**：
  - 401: 无 token / 过期 token / 无效 token
  - 403: 角色权限不足（user 调用 admin 接口）
  - 404: 资源不存在
  - 409: 唯一约束冲突（重复邮箱、重复邀请码）
  - 422: 参数校验失败（格式错误、缺失必填字段）
- **数据隔离测试**：用户 A 不能访问用户 B 的数据（铁律 4 验证）

覆盖率要求：核心模块（TAOR 循环、Middleware Pipeline、Hook System、Permission Engine）≥ 80%。

**后端测试 — AI 接口**：

涉及 Agent 执行链路的接口（POST /tasks → Harness → Agent → Callback）需要专项测试：

- **决策能力测试**：构造复杂场景任务，验证提示词 + 上下文 + 约束条件能否引导 Agent 做出正确决策
  - 场景示例：多步骤任务自动路由到 Coordinator 模式
  - 场景示例：检测到危险操作时触发权限询问
  - 场景示例：Research Agent 不执行写操作
  - Mock 策略：使用 respx mock 模型 API，返回预设的模型响应序列
- **执行能力测试**：工具执行后的结果是否符合预期
  - 场景示例：工具结果超限自动截断
  - 场景示例：工具连续失败触发 Circuit Breaker
  - 场景示例：上下文溢出触发 Compaction
- **边界场景测试**：
  - 循环检测触发（重复工具调用）
  - Guardrail 拦截（违规内容检测）
  - Fork 深度限制触发
  - max_turns 达到上限
  - 模型 API 超时 / 错误码处理

**前端测试 — Playwright E2E**：

每个前端 Task 必须包含 Playwright 测试，双视口同时验证：

- **正常流程测试**：完整业务链路走通
  - 示例：登录 → 创建会话 → 发送消息 → 等待 Agent 流式响应 → 工具卡片展示 → Harness 通知展示 → Run 完成
  - 示例：设置页 → 添加 Provider → 测试连通性 → 设为默认
- **边界场景测试**：预期异常的正确拦截
  - 示例：无效 token → 重定向登录页
  - 示例：SSE 连接断开 → 自动重连 + 恢复消息
  - 示例：超长消息 → 正确渲染不溢出
  - 示例：网络离线 → 错误提示 + 恢复后重试

**模块级任务测试**：

如果一个 Task 同时涉及前端和后端，则前后端测试都必须执行。

### 10.9 开发六原则（强化版）

> 本节为 §10.1 的强化详述版，§10.1 为精简列表，本节为完整规范。

1. **单一职责原则** — 每个服务、类、方法只负责一个明确的职责域，避免职责混乱
2. **最简代码原则** — 不做向后兼容，宁愿破坏性更新也要保证代码最简化，删除所有冗余代码
3. **类型严格原则** — TypeScript 不使用 `any`，Python 使用完整的 type hints，编译/类型检查错误必须立即修复
4. **KISS 原则** — 保持简单直接，如果需要解释就是太复杂了
5. **文档置信度原则** — 绝不基于推测写代码，涉及关键功能时文档置信度不高必须停止并要求准确资料
6. **禁止打补丁原则** — 所有修改必须深度融入代码逻辑，通过重构或调整现有逻辑的方式实现。严禁不从根源解决问题而用补丁绕过。代码过程可以复杂，但最终结果必须是最简洁且完整实现需求的形态

### 10.10 验收流程补充说明

步骤 7 和 8（§10.4）中的 Simplify 和 PJR 为推荐工具。若不可用，则执行等效的手动审查：

- 步骤 7 等效操作：逐文件审查代码复用性、命名一致性、算法效率
- 步骤 8 等效操作：手动运行 `ruff check .`（Python）/ `npx eslint .`（TS）+ `npx tsc --noEmit` + 逻辑走查

---

## 11. 文档体系与开发顺序

### 11.1 文档清单

**基础设施 + Harness 核心层**

| # | 文件名 | 内容 | 依赖 |
|---|--------|------|------|
| 00 | `00-Vision-and-Principles.md` | 本文档 | 无 |
| 01 | `01-System-Architecture.md` | 服务拓扑、DB Schema（14 张表）、PrismMessage、API 总表、SSE 协议、进程策略、目录结构 | DOC-00 |
| 02 | `02-Model-Adapter-and-Prompt-Engine.md` | 双协议 Driver、Prompt 动态装配、Cache boundary、Provider 管理与故障转移 | DOC-01 |
| 03 | `03-Agent-Runtime-and-Harness-Core.md` ⚡重构 | TAOR 主循环、Middleware Pipeline、Hook System（21 事件）、Permission Engine、Guardrails Engine、ContextBudgetManager（4 级 Compaction）、6 层 Memory、Feedback Loop Engine | DOC-02 |
| 04 | `04-Agent-Orchestration.md` | Agent 专业化分工、Fork & Context Isolation、Coordinator-Workers、分布式 Task Scheduler、Agent Teams | DOC-03 |
| 05 | `05-Plugin-Ecosystem.md` | Skill 三级加载、Hook 治理层、MCP 集成、Plugin 命名空间、垂类特调 | DOC-03 |

**后端功能模块（纵向切分，DB → Service → API 完整链路）**

| # | 文件名 | 内容 | 依赖 |
|---|--------|------|------|
| 06 | `06-Backend-Auth-and-User.md` | 用户/邀请码 — 表 + Service + API | DOC-01 |
| 07 | `07-Backend-Session-Run-Task.md` | Session/Run/Message/Queue — 表 + Service + API + SSE + Callback + 子进程调度 | DOC-01, DOC-03 |
| 08 | `08-Backend-IM-Gateway.md` | IM 网关：飞书/企业微信/Telegram 接入、消息路由、渠道配置管理、用户绑定 | DOC-01, DOC-07 |
| 09 | `09-Backend-MCP-Config-Admin.md` | MCP/Provider 配置/用量追踪/审计/Admin — 表 + Service + API | DOC-01 |

**前端（独立，基于已完成的真实 API 开发）**

| # | 文件名 | 内容 | 依赖 |
|---|--------|------|------|
| 10 | `10-Frontend-Foundation.md` | Next.js 搭建、Claude 风格设计系统、组件架构、SSE 封装 | DOC-01 |
| 11 | `11-Frontend-Features.md` | 全部页面实现，逐页对照 Poco 功能清单 | DOC-10, DOC-06/07/08/09 |

**运维 + 可观测性**

| # | 文件名 | 内容 | 依赖 |
|---|--------|------|------|
| 12 | `12-Observability-and-Entropy.md` ⚡新增 | Tracing Pipeline、Token/Cost 追踪、Feedback Loop 闭环、Entropy Detection + Alert、Docker Compose 运维、健康检查 | DOC-03 |

### 11.2 与旧文档体系的变更说明

| 旧文档 | 新归属 | 变更 |
|---|---|---|
| 旧 DOC-03 Agent Runtime Core | 拆为新 DOC-03（Harness Core）+ 新 DOC-04（Orchestration） | Harness 机制从 Agent Runtime 中独立为核心层 |
| 旧 DOC-04 Plugin Ecosystem | 新 DOC-05 | 编号后移，内容不变 |
| 旧 DOC-05~08 后端模块 | 新 DOC-06~09 | 编号后移，内容不变 |
| 旧 DOC-09~10 前端 | 新 DOC-10~11 | 编号后移，内容不变 |
| 旧 DOC-11 运维 | 新 DOC-12，扩展为 Observability + Entropy | 新增 Feedback Loop 闭环和 Entropy 管理 |
| 无 | 新 DOC-03 §Harness | 全新内容：Middleware Pipeline、Guardrails Engine、Permission Engine、Hook 21 事件 |
| 无 | 新 DOC-12 §Entropy | 全新内容：Entropy Detection + Alert + 人工触发清理 |

### 11.3 开发顺序

```
Phase 0 — 设计（不写代码）
  DOC-00 ✅ → DOC-01 → DOC-02 设计部分

Phase 1 — Agent 核心 + Harness（纯后端/引擎层）
  DOC-02（实现） → DOC-03 → DOC-04 → DOC-05

Phase 2 — 后端功能模块（curl 可验证）
  DOC-06 → DOC-07 → DOC-08 → DOC-09

Phase 3 — 前端（基于真实 API 开发，无 Mock）
  DOC-10 → DOC-11

Phase 4 — 可观测性 + 运维封装
  DOC-12
```

### 11.4 每个 Task 的文档结构

每份文档内按 Task 拆分，每个 Task 包含两个部分：

**Part A — 设计与解释**
- 问题陈述（当前缺失什么 / CC 的对标方案是什么）
- 设计决策与理由（含 ADR 编号）
- 数据模型 / 接口定义 / 时序图（如适用）
- 与 CC 架构的映射关系
- Harness 层的交互说明（该 Task 涉及哪些 Harness 子系统）
- 验收标准

**Part B — Claude Code 执行 Prompt**
- Skill 加载指令（必须的 skill 列表）
- 前置条件检查指令
- 分步实现指令（含文件路径、类型定义、函数签名）
- 验证指令（编译检查、测试场景、E2E 指令）
- PROGRESS.md / DECISIONS.md 更新指令

---

## 12. 会话恢复协议

新的 Claude Code 会话开始时，标准恢复序列：

```
1. 读取 docs/00-Vision-and-Principles.md（本文档）     ← 全局纲领 + Harness 哲学
2. 读取 docs/0X-[当前工作文档].md                      ← 当前任务详情
3. 读取 PROGRESS.md                                    ← 最后进度状态
4. 读取 DECISIONS.md                                   ← 架构决策记录
5. git log --oneline -10                               ← 最近提交
6. 执行对应验证命令                                     ← 确认当前状态
7. 加载必需 Skill                                      ← 按场景加载
8. 继续未完成的任务                                     ← 断点恢复
```

---

> **文档维护说明**：本文档是 Prism v2 的全局纲领，在重大架构决策变更时需同步更新。任何与本文档原则冲突的设计必须先修改本文档（并记录 ADR），再执行实现。  
> **重要**：Prism v2 在全新文件夹中从零构建，不继承 v1 的任何代码或目录结构。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-01 System Architecture
