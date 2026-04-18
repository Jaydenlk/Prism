# Prism v2 架构 Review — Batch 1: 总纲层

> **范围**: DOC-00 (Vision) / DOC-01 (Architecture) / DOC-02 (Model & Prompt) + DOC-AUDIT-00-04 + 2026-04-05 PRD v3.1 修订 + 配套 design
> **立场**: 架构挑战者。既定方向内找更优解 + 技术选型可掀桌,但要比原版更合理。
> **评审者**: Claude Opus 4.7(不是 4.6 自审)

---

## TL;DR(给你 30 秒看完)

**根部诊断一句话**: 目标是"5-20 人自托管",但架构按"生产级多租户 Agent OS"设计,规模错配导致整个体系都偏重。

**AUDIT 可信度**: 中等偏上。4.6 看对了大部分实现级 bug(sync/async、ENCRYPTION_KEY、Fork 深度),但**完全没看到架构级的根部问题**,还给 DOC-00/01 打 9/10,给全文一句"核心架构方向正确"——这是 4.6 降智期最明显的盲区。

**PRD v3.1 修订方向**: 审计修补部分大多数 OK,但**新增 7 个 Task 而一个没砍**——AUDIT 自己提出"Hook 21 事件过多/Memory 6 层太重/DOC-03 最大风险单点",v3.1 的响应不是减法而是又加了 Task 3.6/4.5/5.5/5.6/5.7/9.3/11.5。scope 继续失控。

**我的建议关键词**: **砍半、单点 Harness、回调改批缓冲、SSE ticket、Obs 前移**。

---

## 1. AUDIT 反审 — 4.6 看对了什么,漏了什么

### 1.1 AUDIT 看对的(保留,不用改)

| AUDIT 条目 | 我的判断 | 说明 |
|---|---|---|
| P0-2 sync/async 边界不明确 | ✓ 真问题 | Executor 启动 sync + 运行时 async,必须明说 |
| P0-3 ENCRYPTION_KEY 独立于 JWT_SECRET | ✓ 真问题 | 密钥职责分离是基本安全原则 |
| P0-4 Fork 深度限制 | ✓ 真问题 | 无限嵌套 fork 会爆内存 |
| P1-4 promote 原子性 | ✓ 真问题 | Backend 崩溃会丢队列消息 |
| P1-7 DOC-03 最大风险单点 | ✓ 真问题 | Task 间依赖不灵活确实是 blocker |
| P1-8 Hook 21 事件过多 | ✓ 真问题 | Phase 1 用不到 13 个 |
| P1-9 Memory 6 层过重 | ✓ 真问题 | 先做 2 层足够 |
| P1-10 Plan.parse 脆弱 | ✓ 真问题 | LLM 输出解析不可靠是经典问题 |

**评**: 4.6 的实现级 bug 发现能力是在线的。这部分保留即可。

### 1.2 AUDIT 看偏的(要换视角)

| AUDIT 判断 | 我的反驳 |
|---|---|
| DOC-00 打 9/10 "愿景清晰、原则有约束力" | 愿景和原则写得漂亮,但与实际 scope 脱钩。原则 P1 说"不是聊天转发器",但 DOC-00 §5.1 的 5 层架构 + §2.5 的 3 个 IM 通道 + §9.5 的 4 级能力适配 + 铁律 4 道强制,这不是"不当转发器",这是"要当 OS + SaaS 平台 + 合规审计系统"。评分应该扣架构规模分。 |
| DOC-01 打 9/10 "14 表精确、API 路由完整" | 14 表**看起来**精确,但漏了 Skills 安装表(§6.12 有 Skills API 却没对应表)、漏了 Prompt Cache 用量字段(`runs.input_tokens/output_tokens` 没有 `cache_hit/miss/creation_tokens`)、`providers.user_id = admin` 是 hack 不是设计。应该扣表设计完整性分。 |
| "核心架构方向正确" | 方向对(Harness 哲学、双协议、自托管)**不等于**架构正确(5 层、Harness 双实例、3 IM 通道必做)。把方向正确误当成架构正确,是最大的盲区。 |
| Task 拆分粒度合理 | 每个 Task 的 Part B 全是长 Prompt 指令,本质是"一条路走到黑",中途出错没法 rollback 到 Task 粒度。只有完整跑起来才能验收 —— 这不是合理粒度,是伪粒度。 |

### 1.3 AUDIT 完全漏掉的根部问题(P0 级)

这是 4.6 自审的盲区,需要 4.7 独立加:

| # | 问题 | 严重性 | 所属文档 |
|---|---|---|---|
| **R1** | **规模错配** — 5-20 人自托管 vs 生产级多租户架构 | 架构根部 | DOC-00/01 全体 |
| **R2** | **Layer 3 Harness 双实例** — Backend 和子进程各跑一份,状态通过 Redis 同步,职责边界不清 | 设计缺陷 | DOC-01 §2.1 vs §3.1 |
| **R3** | **Backend↔Executor 回调风暴** — text_delta 每 token 一次 HTTP,2C2G 单进程下 CPU 吃爆 | 性能 | DOC-01 §9.1 |
| **R4** | **SSE JWT 走 URL query** — JWT 进 Nginx 日志、浏览器历史、CDN 缓存,标准做法是换短期 ticket | 安全 | DOC-01 §7.2 |
| **R5** | **Phase 顺序 Obs 放最后** — Phase 1-3 盲飞,Phase 4 才能看到系统真实行为 | 流程 | DOC-00 §11.3 |
| **R6** | **Prompt Cache 命中率追踪缺失** — DOC-00 §9.5 强调 Cache 是优化重点,但 `runs` 表缺 cache 字段,无法度量 | 成本观测 | DOC-01 §4.2 |
| **R7** | **Skills 持久化表缺失** — §6.12 有 6 个 Skills API,14 表里没对应表 | 数据模型漏洞 | DOC-01 §4.2 |
| **R8** | **子进程"隔离"是假隔离** — 仅降权用户 + 白名单 DNS,无 cgroup/namespace,逃逸容易 | 安全 | DOC-00 §8.1 + DOC-01 §3.2 |
| **R9** | **`providers.user_id = admin` 建模 hack** | 数据模型 | DOC-01 §4.2 |
| **R10** | **`im_bindings` 群聊建模缺失** — 同一用户跨多个群聊没有多条绑定空间 | 数据模型 | DOC-01 §4.2 |
| **R11** | **Harness 运行时配置热更新语义未定义** — `/harness/config/reload` 影响正在跑的 Run 吗?子进程怎么感知配置变了?DOC-01 §6.10 有 API,无语义 | 功能语义 | DOC-01 §6.10 |
| **R12** | **Session `config_snapshot` vs Run `model/provider_id` 优先级未定义** — 用户中途改 model 时新 Run 用谁? | 功能语义 | DOC-01 §4.2 |

---

## 2. v3.1 修订方向的判断

v3.1 的三类修订:

### 2.1 ✓ 正确方向(接受)

- AUDIT 的 P0/P1 修补绝大多数都是对的,继续做
- DOC-00 §10.8 加 pytest + Playwright + respx 测试规范,方向正确
- ADR 重编号,文档工程卫生

### 2.2 ⚠ 方向对但做法偏

| 修订项 | 问题 |
|---|---|
| **Task 3.6 Harness 动态更新** | 思路对(底层固化 + 垂类热更新),但当前阶段 0 用户、0 垂类,谈"垂类热更新"是把 V2 的能力塞进 V1 — 违反 DOC-00 P7 Build to Delete。**建议**: Phase 1 只做"平台级规则硬编码 + 插件声明式注册",不做 HarnessConfigManager + yaml + `/harness/config` API + UI 整套。yaml 热更新可以在 Phase 3+ 有实际垂类需求时再做。 |
| **Task 4.5 PluginBuilder Agent** | "强制最少 5 轮需求收集"这个是产品流程,不是系统级防御。把它写成 Middleware + Guardrail 硬编码,违反 DOC-00 P5 配置驱动。**建议**: Prompt 模板 + 前端向导表单就够了,5 轮对话靠 Agent prompt 引导,不靠 platform_rules.py 硬卡 |
| **Task 5.5-5.7 Skills Market** | 5-20 人自托管系统不需要"多源聚合 + CC 协议兼容 + CLI + Agent Tool + UI 商店"一整套。**建议**: Phase 1 只做"本地安装 skill + yaml 声明",Phase 2 再做单源搜索(只从 Anthropic 官方或一个社区源),CC 协议兼容等真有 CC 插件生态再说 |

### 2.3 ✗ 方向错(拒绝)

- **新增 7 个 Task 而不砍** — 最大问题。AUDIT 自己判断 DOC-03 已是最大风险单点、Hook 21 过多、Memory 6 层过重,v3.1 的正确响应是**用审计修补抵消新功能**,而不是**审计修补 + 新功能同时加**。当前 v3.1 的实际净 scope 是 **+ 7 个 Task**,scope 继续失控。
- **§10.8 测试规范没有 CI 绑定** — 写成"每个 Task 完成时必须全过",但谁跑、哪个 CI、失败怎么办没写。在真实 CC 项目里从未见过"规范没 CI 却能执行"的情况。这条如果不绑 GitHub Actions / pre-commit,就是装饰性条款。

---

## 3. 架构级根部建议

下面是用"既定方向内找更优解 + 可掀桌技术选型"的尺度,我给出的根部建议。

### 3.1 砍半原则 — 先让 V1 能生、再让 V2 能飞

> 当前的 v3/v3.1 是一份 V2 的完整愿景,但 AUDIT 自己就说"Task 间最小可行依赖"。一个**真正 Phase 1 能交付**的 scope 应该是下面这个。

| 模块 | 当前 scope | 建议 Phase 1 scope | 推迟到何时 |
|---|---|---|---|
| 架构层数 | 5 层 (L1-L5) | 4 层(合 L2+L3 为 Orchestration/Harness) | L3 独立是否真有必要,Phase 2 看监控数据再定 |
| IM 通道 | 飞书 + 企微 + Telegram | **只飞书** | 企微/TG 等有具体用户需求再加 |
| Hook 事件 | 21 | **8**(SessionStart/End、PreToolUse、PostToolUse、PostToolUseFailure、SubAgentStart/Stop、Notification) | 13 个剩余事件按需 |
| Memory 层 | 6 层 | **2 层**(session + user) | project/skill/team 按需 |
| Compaction 级 | 4 级 | **2 级**(auto-compact + reactive truncation) | micro-compact 和 session-memory 作为 Phase 2 优化 |
| Agent 类型 | General + Research + Planner + Verifier | **General + Research** | Planner/Verifier 等 Coordinator 模式真跑起来再加 |
| Coordinator 模式 | 默认能力 | **可选,默认关** | 有复杂多步骤任务测试用例再激活 |
| Provider 预设 | 50+(cc-switch 量级) | **5-8 个**(Anthropic / OpenAI / MiniMax / DeepSeek / Kimi / Qwen / Gemini) | 参考 cc-switch 列表扩展 |
| 熵管理 | 检测 + 告警 + 人工触发 | **日志 + 周期性审阅** | 熵检测系统是 Phase 3+ 产物 |

**核心理念**: Harness 哲学必须在 Phase 1 内建(不能是后期补),但 Harness 具体子系统的数量和深度应该最小化。

### 3.2 Executor 架构重审

#### 问题
DOC-01 §2.1 说"Harness Runtime 在 Backend 进程内",§3.1 又说"子进程内的 Harness Runtime 独立实例"。**两份 Harness 同时存在,职责不清**:
- Middleware Pipeline 每次 TAOR 循环要跑,在哪边跑?
- PermissionEngine 做 `ask`(人工确认)决策时,需要暂停子进程等用户回答,Backend 怎么暂停子进程?
- CircuitBreaker 状态靠 Redis 共享——那 Middleware 状态(§9.2)也靠 Redis,实际上两份 Harness 都在"读同一个 Redis",那 Backend 那份还需要吗?

#### 建议
**只保留子进程内的 Harness,Backend 进程里去掉 Harness 实例**。Backend 的角色变成:
1. API + 编排 + 回调聚合(不跑 Middleware / Hook / Guardrail)
2. 只负责把子进程上报的 `harness_event` 持久化 + SSE 推送
3. 如果将来要做"Pre-Run 护栏"(在子进程启动前就拦截),那可以加一层轻量 API 级 Guardrail,但不要叫 Harness Runtime

这样 Layer 3 在架构图上只出现在子进程里,Backend 只有 Layer 1 + 2 + 5,概念上更清晰。

### 3.3 回调协议重构

#### 问题
每个 `text_delta` 都发 HTTP 回调。模型一秒几十个 token,一次 Run 几分钟,回调量到千级。2C2G 下 FastAPI + Uvicorn 处理这个量,CPU 会被 HTTP 解析+JSON parse+DB 写吃爆。同时 Backend 每次回调都要转 SSE 推送,整个链路 Python → HTTP → Python → Redis pub → SSE,延迟放大。

#### 建议
**三选一,不兼容,挑一个**:

**方案 A(推荐)**: Redis Pub/Sub 直通,HTTP 回调只做关键事件
- 子进程把 `text_delta` 直接 publish 到 `sse:{session_id}`,Backend SSE 订阅直接转发
- HTTP 回调只用于"需要 Backend 处理业务逻辑"的事件(tool_end 要持久化到 DB、run_complete 要推进队列、harness_event 要写审计)
- 好处: 流式延迟降到 Redis 级,CPU 省 70%+

**方案 B**: HTTP batch
- 子进程把 100ms 内的所有 text_delta 合并成一批再发
- 好处: 不改协议栈,改动小
- 坏处: 用户体验上打字延迟会加 50-100ms

**方案 C**: WebSocket 双向
- 子进程和 Backend 保持 WebSocket 长连接,双向推送
- 好处: 支持 Backend → 子进程反向通知(比如 admin 热更新 Harness 配置)
- 坏处: 最复杂,单机场景性价比低

不推荐现状的每 token HTTP。

### 3.4 SSE 认证重构

当前 `GET /sessions/{id}/stream?token={JWT}` 把 JWT 放 URL query,会进:
- Nginx access.log
- 浏览器历史
- 反向代理的任何一层日志
- 如果是公网部署,CDN 缓存 key 可能包含 query

#### 建议
- 新增 API `POST /auth/sse-ticket` 返回 60 秒一次性 token,用完作废
- SSE 连接改成 `?ticket=xxx`,服务端验证后立即从 Redis 删除
- JWT 不再出现在 URL

### 3.5 Phase 顺序调整

当前:
```
Phase 0 设计 → Phase 1 Agent 核心 → Phase 2 Backend → Phase 3 Frontend → Phase 4 Obs
```

问题: Phase 1 实现 Harness 而不实现 Obs,是盲飞。Hook/Middleware/Guardrail 跑了什么、触发了什么、延迟多少,Phase 4 才能看见。期间出的任何 bug 都没有可观测性可以 debug。

#### 建议
```
Phase 0 设计 → Phase 1 Agent 核心 + Obs 最小子集(trace + runs 统计 + audit_logs) → Phase 2 Backend → Phase 3 Frontend → Phase 4 Obs 增强(熵检测、可视化、聚合分析)
```

**Phase 1 包进 Obs 最小子集**:
- `audit_logs.harness.*` 事件写入(已在 schema 里,实现就好)
- `runs.harness_summary` JSONB 填写
- 结构化日志(JSON log)到 stdout,Docker 日志可看
- **不包含**熵检测、告警、前端仪表盘

### 3.6 数据模型补丁

加到 14 表里(或抽到 16 表):

**`runs` 表新增字段**:
```sql
cache_hit_tokens INT NULL       -- Anthropic Prompt Cache 命中
cache_miss_tokens INT NULL      -- Cache miss
cache_creation_tokens INT NULL  -- Cache 创建(首次写入缓存)
```

**新增 `skill_installs` 表**(对应 §6.12):
```sql
id UUIDv7 PK
user_id FK → users.id
skill_name VARCHAR(100)   -- skill 全名(含命名空间)
source VARCHAR(50)        -- 'local' | 'official' | 'community' 等
version VARCHAR(50)
installed_at TIMESTAMPTZ
metadata JSONB            -- SKILL.md frontmatter 缓存
UNIQUE(user_id, skill_name)
```

**`providers` 表改动**:
```sql
-- 删除 user_id hack
-- 新增:
scope VARCHAR(20) NOT NULL   -- 'system' | 'user'
user_id FK → users.id ON DELETE CASCADE NULL   -- scope='user' 时填,'system' 时 NULL
```

**`im_bindings` 表改动**(支持群聊):
```sql
-- 现有唯一约束改为 (channel, platform_user_id, platform_chat_id)
-- platform_chat_id 为 NULL 表示单聊,有值表示群聊场景
```

### 3.7 其他小修

- **`MAX_TURNS_PER_RUN = 50`** 对 2C2G 太高。CC 默认 30,Codex 更低。建议改 **30**。
- **`MAX_CONCURRENT_RUNS = 2`** + 2C2G 是临界,推荐配置应写 **4C4G / 3 Runs**,2C2G 只作为"MAX_RUNS=1"下的最低配置(和 AUDIT P2-1 同结论,但要更明确)。
- **`.env.example` 三件套**: `JWT_SECRET` / `CALLBACK_SECRET` / `ENCRYPTION_KEY` 必须分离,生产环境启动时如果发现任意两个值相同,直接 refuse boot。
- **`RUN_TIMEOUT_SECONDS = 600`** 对 Coordinator 多步骤任务可能不够,但对简单对话又太长。建议按 agent_type 分档: general=300, research=600, planner=180, coordinator=1200。

---

## 4. 结论 & 给你的选择

### 4.1 Batch 1 阶段的结论

- AUDIT-00-04 的**实现级修补 95% 接受**,但架构级盲区需要用 R1-R12 12 项补上
- PRD v3.1 **审计修补 OK**,但**新增 7 个 Task 全部推迟或降级**——先让 Phase 1 的砍半版能交付,再考虑加功能
- DOC-00 / 01 / 02 的**架构根部**需要动:Executor 架构重审(§3.2)、回调协议改造(§3.3)、SSE 认证(§3.4)、Phase 顺序(§3.5)、数据模型补丁(§3.6)

### 4.2 要你决策的分歧项

在进入 Batch 2 之前,以下 5 个决策我需要你确认,否则后续 review 方向会跑偏:

**D1 — 架构规模**: 接受"砍半版"作为 Phase 1 新基线?(4 层 / 8 Hook / 2 Memory / 2 Compaction / 2 Agent / 1 IM / 5-8 Provider)
- 选项: (a) 全接受 (b) 部分接受(说明哪几项不砍) (c) 反对,保留原 scope

**D2 — Layer 3 Harness**: 只保留子进程内 Harness,Backend 去 Harness 实例?
- 选项: (a) 同意 (b) 反对,Backend 必须有 Harness(说明理由) (c) 再讨论

**D3 — 回调协议**: 改造成 Redis 直通 + HTTP 关键事件(方案 A)?
- 选项: (a) 方案 A (b) 方案 B batch (c) 方案 C WebSocket (d) 保留现状

**D4 — v3.1 新增 Task**: 7 个新 Task(3.6/4.5/5.5/5.6/5.7/9.3/11.5)全部推迟到 Phase 2+?
- 选项: (a) 全推迟 (b) 只保留最简版(哪几个、最简到什么程度) (c) 保留所有

**D5 — Phase 1 包 Obs 最小子集**: 同意 Phase 1 必须包含结构化日志 + harness_summary + audit_logs 写入?
- 选项: (a) 同意 (b) 反对,Obs 完全推迟 (c) 再讨论

---

> **下一步**: 等你回答 D1-D5 后,进入 Batch 2(DOC-03/04/05 Agent 核心)。
> **本 Batch 覆盖的文档**: DOC-00 (44KB) / DOC-01 (50KB) / DOC-02 (50KB) / DOC-AUDIT-00-04 (20KB) / PRD v3.1 (62KB) / PRD-design (57KB) = 283KB
