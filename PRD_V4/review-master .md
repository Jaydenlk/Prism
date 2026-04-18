# Prism v2 — Master Review

> **定位**: 跨 Batch 总 review + 改写阶段总纲 + 13 份 PRD 改写优先级
> **输入**: Batch 1 v2 + Batch 2 + Batch 3 + Batch 4 + Batch 5 + PDF 补丁 + 用户历史要求归档
> **读者**: 用户 + 改写阶段的自己(下一步要按这份做)
> **评审者**: Claude Opus 4.7
> **日期**: 审查结束,改写前

---

## 0. Review 阶段的最终判断

### 0.1 一句话结论

**这份 PRD 体系**(14 份 + 3 份补充)的**架构方向完全正确**,但**执行细节的密度、一致性、CC fidelity 和质量规范的可操作性还差一个量级**,直接给 Sonnet 4.6 按当前版本写代码,会写出 80% 能跑但 20% 经典 bug、15% 架构偏差、10% 协议空洞的系统。

### 0.2 项目本质校准

经过 5 个 Batch + PDF + 历史记录挖掘,我对 Prism v2 的最终定位:

```
Prism v2 = 
    Manus 的产品体验(多步骤任务拆分 + 双入口 Web/IM + 自托管)
  × Claude Code 的架构深度(Agent OS + Harness + 专业化 Agent + Skill/Plugin 生态)
  × 主权工具的运维简洁(4C8G 够用 / Docker Compose / 开箱 Grafana)
```

三者**都是锚点**,不是"主要对标 + 参考"。改写阶段每个设计决策都要对三个锚点做压力测试:
- Manus 有没有这个功能?怎么做的?
- CC 有没有?源码在哪?
- 自托管场景下复杂度能否控制?

### 0.3 5 个 Batch 的问题量级汇总

| Batch | 覆盖 | 实现级问题 | 架构级问题 | 新 Task 修订 |
|---|---|---:|---:|---:|
| **B1 v2** | DOC-00/01/02 + AUDIT + v3.1 | 15 | 7 | — |
| **B2** | DOC-03/04/05 | 22 | 5 | 5 个(3.6/4.5/5.5/5.6/5.7) |
| **B3** | DOC-06/07/08/09 | 17 | 5 | 1 个(9.3) |
| **B4** | DOC-10/11 + UI | 17 | 5 | 1 个(11.5) |
| **B5** | DOC-12 | 7 | 5 | 新增 4 个 Task(12.4/12.5/12.6/12.7) |
| **PDF 补丁** | 跨文档 | 10 | — | — |
| **合计** | 17 份 | **88** | **27** | **11** |

**115 个点需要在改写阶段落地**。这是真实工作量。

---

## 1. 跨 Batch 一致性问题汇总

这些问题在单个 Batch 里看不清,需要全景视图才暴露。按严重度排序。

### M1 — 📛 permission="ask" 反向通信协议(跨 B2/B3/B4)

- **B2 §A3-7** 在 DOC-03 Hook System 里发现这个协议完全未定义
- **B3 §A7-5** 在 DOC-07 里要求 Backend 新增 `POST /sessions/{id}/permission-answer` 端点 + Redis BLPOP
- **B4 §B4-3** 在 DOC-11 里要求前端有对应的弹窗 UX
- **B5** Prometheus metrics 要采集 `prism_permission_ask_wait_seconds`

**改写影响**: 这 **1 个协议空洞** 要同时改 DOC-03 / DOC-07 / DOC-11 / DOC-12 四份文档,每份文档都要讲清楚自己这一层的职责。

### M2 — 📛 回调协议从 HTTP 全量改为 Redis 流式直通(跨 B1/B2/B3/B4)

- **B1 §3.3 + §D3** 决策了方案 A(Redis 直通流式事件 + HTTP 关键事件)
- **B2 §A3-4** 在 DOC-03 BackendCallback 里要改 `emit()` 实现
- **B3 §B3-3** 在 DOC-07 CallbackService 里要改接收方职责
- **B4 §B4-III** 在 DOC-10 SSE Client 里前端订阅模型要同步改

**改写影响**: 回调协议是 **CORE 协议级变更**,要同时改:
- DOC-01 §9.1 跨层通信契约(文档层)
- DOC-03 BackendCallback(子进程 emit)
- DOC-07 Callback Service / SSE Manager(Backend 接收和转发)
- DOC-10 SSE Client(前端订阅)
- DOC-12 Prometheus metrics(新增 Redis publish / SSE forward 耗时)

### M3 — 📛 子进程崩溃恢复全链路缺失(跨 B2/B3/B5)

- **B2 §B-2** 在 DOC-03/04 发现"心跳监控 + 恢复策略"全线缺失
- **B3 §A7-6** 在 DOC-07 里要补 `HeartbeatMonitor` 后台任务 + `AgentRecoveryService`
- **B5 §B5-I** Prometheus metrics 要有 `prism_agent_heartbeat_stale_total` 和 `prism_agent_subprocess_crashed_total`

**改写影响**: 这是生产可靠性的底线,涉及:
- DOC-01 跨层通信契约(Heartbeat key 命名规范)
- DOC-03 子进程心跳写入逻辑
- DOC-04 Coordinator 恢复语义 + coordinator_plans 表
- DOC-07 Backend HeartbeatMonitor 实现 + Run status 自恢复
- DOC-12 心跳监控 metrics

### M4 — 📛 Schema 变更的跨文档影响(跨 B1/B2/B3/B4/B5)

Batch 1 v2 §3.5 + Batch 2 / 3 / 4 / 5 提出的 Schema 修改清单:

| 修改 | 影响文档 |
|---|---|
| `runs` 表加 `cache_hit_tokens` / `cache_miss_tokens` / `cache_creation_tokens` / `harness_version` / `agent_type` / `run_mode` / `parent_run_id` | DOC-01, DOC-03(写入), DOC-07(查询), DOC-11(展示), DOC-12(聚合) |
| 新增 `skill_installs` 表 | DOC-01, DOC-05(CRUD), DOC-09(API) |
| 新增 `coordinator_plans` 表 | DOC-01, DOC-04(checkpoint), DOC-07(恢复) |
| 新增 `permission_requests` 表(或改用 Redis)| DOC-01, DOC-03, DOC-07 |
| 新增 `im_message_dedup` 表或 Redis | DOC-01, DOC-08 |
| `providers` 表改 `scope` 字段,删除 user_id=admin hack | DOC-01, DOC-02(Provider Manager), DOC-09 |
| `im_bindings` 唯一约束改成 `(channel, platform_user_id, platform_chat_id)` | DOC-01, DOC-08 |
| `messages` 表规范化 `text_preview` 生成规则 | DOC-01, DOC-07 |
| `users` 表加 `memory TEXT`(或新增 `user_memories` 表) | DOC-01, DOC-03 Task 3.5 Memory |
| `sessions` 表明确 `config_snapshot` 语义(Session 创建时快照 vs Run 级动态) | DOC-01, DOC-07, DOC-11 |

**改写影响**: DOC-01 的 §4.2(表清单)需要**从 14 张扩展到 17-20 张**,所有其他文档引用表的地方都要同步更新。

### M5 — 📛 Obs 前移到 Phase 1 的全文档影响(跨 B1/B5)

Batch 1 §3.4 + Batch 5 §B5-I 决策: Obs 在 Phase 1 就完整实现,不接受"最小子集"。

**改写影响**: 每个 Task 的 Part B 都要加:
- 结构化日志采集点(`logger.info("event.name", **context)`)
- Prometheus metrics 采集点(`metric.labels(...).observe(duration)` / `.inc()`)
- OTel trace span(`with tracer.start_as_current_span("operation"):`)

这不是装饰性要求,是**每个函数/方法**都要带。改写时如果漏,Obs 就是假的。

### M6 — Frontend 三份文档的关系必须明示(B4 §B4-I)

DOC-10 / DOC-11 / UI design spec 三份同时存在,优先级和一致性规则当前不清楚。

**改写影响**: 改写阶段必须在 DOC-10 开头写明(具体内容见 B4 §B4-I):
- UI design spec = 视觉真相源,不得修改
- DOC-10 = 技术基建
- DOC-11 = 业务功能,业务逻辑真相源
- 冲突时的优先级决议规则

### M7 — Cache 命中率是核心成本指标(跨 B1/B3/B5)

- B1 §3.6 schema 加了 cache tokens 字段
- B3 §A9-3 Provider Manager 要报 cache 命中率
- B5 §A12-3 HarnessAnalytics.aggregate() 要返回 cache_stats

**改写影响**: 前端用量仪表盘(DOC-11 Task 11.4)要新增"Cache 节省金额"汇总卡,Grafana dashboard 要有 Cache 命中率时序图。

### M8 — v3.1 新增 7 Task 的做法偏差(跨 B2/B4)

B2/B4 都发现 v3.1 新增 Task 保留没问题(全保留),**但每个 Task 的做法需要修正**:

| Task | 主要做法修订 |
|---|---|
| 3.6 HarnessConfigManager | 4 源砍到 2 源,删 PATCH API 和 toggle_middleware 运行时开关 |
| 4.5 PluginBuilder | "5 轮对话"改"需求完整度打分",platform Guardrail 降级为可配置 |
| 5.5 Skills Registry | Phase 1 只上 Local + GitHub 两源,Phase 2 再加 npm / Manus |
| 5.6 Skills CLI + Agent Tool | Agent Tool 只保留 search,不给 install 权限 |
| 5.7 CC 插件兼容层 | export_to_cc 返回 ConversionReport,plugin.yaml schema 严格化 |
| 9.3 Admin 审计 | Part B 需要完整补全(当前缺失) |
| 11.5 Skills Store UI | 拆分为 Skills Store / Plugin Builder / Harness Config 三个子页 |

**改写影响**: 这些 Task 都是**扩充**而非推倒重来,但密度和严谨度需要大幅提升。

---

## 2. 改写优先级分级

按"**不改会导致 Sonnet 4.6 写错 / 写不出 / 写偏**"的严重度分 P0/P1/P2。

### P0 — 必改(不改就不能开始写代码)

| # | 改动内容 | 涉及文档 |
|---|---|---|
| P0-1 | permission="ask" 反向通信协议完整定义(Redis BLPOP + 专用端点) | DOC-03, DOC-07, DOC-11, DOC-12 |
| P0-2 | 回调协议改为 Redis 流式直通 + HTTP 关键事件 | DOC-01 §9.1, DOC-03, DOC-07, DOC-10, DOC-12 |
| P0-3 | 子进程崩溃恢复机制(心跳 + 自动 promote + coordinator 恢复) | DOC-01, DOC-03, DOC-04, DOC-07, DOC-12 |
| P0-4 | Schema 扩展(runs 新字段 + 新增 4-5 张表) | DOC-01 §4.2 全面重写 |
| P0-5 | Harness 架构单实例化(Backend 去 Harness,只在子进程) | DOC-01 §2.1, DOC-03 全文 |
| P0-6 | Compaction tool_use↔tool_result 配对保护算法 | DOC-03 Task 3.5 |
| P0-7 | 工具并发执行(asyncio.gather)替代串行 for | DOC-03 Task 3.1 |
| P0-8 | HookDecision 完整字段定义 + 合并规则明文(11 字段) | DOC-03 Task 3.3 |
| P0-9 | DOC-10 Task 10.2/10.3 从"几行简述"扩展到完整实现规范 | DOC-10 |
| P0-10 | DOC-12 从 3 Task 扩展到 7 Task(加 Prometheus/OTel/结构化日志/前端上报) | DOC-12 |
| P0-11 | ENCRYPTION_KEY / JWT_SECRET / CALLBACK_SECRET 三独立 + 启动校验 | DOC-00, DOC-01, DOC-06 |
| P0-12 | SSE Ticket(替代 JWT 走 URL query) | DOC-01 §7.2, DOC-07, DOC-10 |
| P0-13 | Frontend 三份文档关系明示 | DOC-10 前言 |
| P0-14 | IM Webhook 幂等性(Redis 缓存 + 去重) | DOC-08 |
| P0-15 | Prompt Section 粒度对齐 CC 的 10+ getter(不是当前的 7+4) | DOC-02 Task 2.4 |
| P0-16 | TokenEstimator 直接上精确 tokenizer(不接受 Phase 2 切换) | DOC-02, DOC-12 |
| P0-17 | message.sequence_no 并发冲突解决(DB 序列 + advisory lock) | DOC-07 |

### P1 — 强推荐(不改会有明显质量问题,但不阻塞开工)

| # | 改动内容 | 涉及文档 |
|---|---|---|
| P1-1 | Verification Agent 完整 prompt(VERDICT 强制格式 + "try to break it" 反制) | DOC-04 Task 4.1 |
| P1-2 | Fork Agent capability-based 白名单 + prompt-level 行为约束 | DOC-04 Task 4.2 |
| P1-3 | Agent-specific MCP servers + frontmatter skills | DOC-04 Task 4.1 |
| P1-4 | Fork Briefing 结构化(ForkBriefing dataclass 强制) | DOC-04 Task 4.2 |
| P1-5 | Coordinator Plan 持久化 + 恢复接口 | DOC-04 Task 4.3, DOC-07 |
| P1-6 | PluginBuilder 需求完整度打分(替代硬编码 5 轮) | DOC-04 Task 4.5 |
| P1-7 | Skills Registry 只上 2 源(Local + GitHub) | DOC-05 Task 5.5 |
| P1-8 | Skills Agent Tool 只保留 search | DOC-05 Task 5.6 |
| P1-9 | Task 3.6 HarnessConfigManager 简化(2 源 + 删 API) | DOC-03 Task 3.6 |
| P1-10 | Task 9.3 Admin 审计 Part B 完整补全 | DOC-09 |
| P1-11 | Task 11.5 拆分为 3 个子页 | DOC-11 |
| P1-12 | Entropy Detection 5 信号扩展到 8 信号 + 阈值校准机制 | DOC-12 Task 12.2 |
| P1-13 | /health 端点拆分 liveness/readiness/detailed | DOC-12 Task 12.3 |
| P1-14 | 告警通道定义(AlertDispatcher + IM 告警 + 邮件) | DOC-12 Task 12.4(新) |
| P1-15 | 结构化日志规范全 PRD 统一(structlog + JSON) | DOC-12 Task 12.6(新), 全文 |
| P1-16 | 运行时变量替换系统(${PRISM_PLUGIN_ROOT} 等) | DOC-05 Task 5.7 |
| P1-17 | MCP instructions 注入 PromptAssembler 动态 section | DOC-02, DOC-05 |
| P1-18 | Skill 必须执行的强制语义(skill_grammar_section) | DOC-05 Task 5.1 |
| P1-19 | SSE 事件处理状态机 + 消息 merge 策略 | DOC-10 |
| P1-20 | MAX_TURNS / RUN_TIMEOUT 按 agent_type 分档 | DOC-01 §11.3 |

### P2 — 有余力做(改善但不关键)

| # | 改动内容 | 涉及文档 |
|---|---|---|
| P2-1 | TaskRouter 双层(关键词 + LLM 分类 fallback) | DOC-04 Task 4.4 |
| P2-2 | Background Agent 模式设计(Phase 2 预留) | DOC-04 §4.6 |
| P2-3 | User Memory 持久化表设计 | DOC-01, DOC-03 Task 3.5 |
| P2-4 | Docker Compose 资源限制统一 | DOC-01, DOC-12 |
| P2-5 | 前端 Sentry / 自建错误监控选项 | DOC-12 Task 12.7(新) |
| P2-6 | Playwright E2E 样例脚本(每个前端 Task) | DOC-11 全部 |
| P2-7 | Grafana Dashboard JSON 模板 | DOC-12 Task 12.4(新) |

---

## 3. 改写阶段的工作流设计

### 3.1 节奏(已与用户确认)

```
阶段 A — 先导文档起草(1 份)
  DOC-CC-ONBOARDING.md (新文件)
  用户校验方向,必要时微调
  └─ 确认 ✅

阶段 B — 13 份 PRD 逐份改写
  B.1  改写基础层: DOC-00 / DOC-01 / DOC-02(互相引用频繁,一起改)
  B.2  改写 Agent 核心: DOC-03 / DOC-04 / DOC-05(一起改)
  B.3  改写 Backend: DOC-06 / DOC-07 / DOC-08 / DOC-09(一起改)
  B.4  改写 Frontend: DOC-10 / DOC-11(一起改,UI design spec 不动)
  B.5  改写 Obs: DOC-12(单份,但要新增 4 个 Task)

阶段 C — 最终校验
  C.1  跨文档一致性检查(ADR 编号 / Schema / API 路由 / SSE 事件)
  C.2  生成 checklist(所有 115 个修改点的落地确认)
  C.3  最终交付
```

### 3.2 每份 PRD 的改写流程(固定 SOP)

对每份 PRD 的改写采用以下 **6 步**:

**Step 1 — 读原文**: 完整读 `/mnt/project/` 对应文件,了解当前内容
**Step 2 — 查 review**: 在 Batch 1-5 + 补丁 + 归档里找到该文档的所有问题点
**Step 3 — 查 PDF**: 如果涉及 CC 映射,从 PDF 找原文确认
**Step 4 — 起草**: 按"Part A 设计 + Part B Prompt"格式写新版,密度达标
**Step 5 — 自检**: 用"落地确认 checklist"检查所有相关 P0/P1 是否都体现
**Step 6 — 交付**: 落盘 outputs,present_files 给用户

### 3.3 每份 PRD 的质量标准(硬底线)

基于 `user-preferences-archive.md` 十二条要求,每份 PRD 必须满足:

- **密度标准**: Sonnet 4.6 看完能零猜测地开写。没有"按 CC 思路实现"这种模糊话
- **结构标准**: 每个 Task 都是 Part A + Part B 双节结构
- **Part A 必含**: 问题陈述 / CC 架构映射(引用具体 src/ 文件) / ADR 号 / 数据模型 / Harness 交互 / 验收标准
- **Part B 必含**: 上下文 / Skill 加载指令 / 前置条件检查 / 文件创建目录树 / 实现规范(精确到函数签名) / 验证步骤(含期望输出) / 完成后(PROGRESS + DECISIONS + commit)
- **代码骨架标准**: 所有接口、dataclass、核心函数都要有可直接 copy 的骨架,不省略
- **陷阱标记**: 遇到"4.6 容易犯错"的点,用 `> ⚠️ 陷阱:` 块显式警告
- **断点恢复**: 每个 Task 要有"中断后如何恢复到该 Task"的指引

### 3.4 质量自检 Checklist

改写每份 PRD 后跑一遍:

```
[ ] 所有 P0(与本文档相关)已落地
[ ] 所有 P1(与本文档相关)已落地,或明确标注"Phase 2"
[ ] Part A 每节完整(6 个标题不缺)
[ ] Part B 每节完整(7 个标题不缺)
[ ] 代码骨架可直接 copy(无 `...` 省略,无 `TODO` 占位)
[ ] 所有引用的表/API/Service/ADR 编号准确
[ ] 所有 CC 源码引用有具体文件路径(如 `src/tools/AgentTool/runAgent.ts`)
[ ] 验证步骤含期望输出(不是"应该成功")
[ ] 陷阱清单列出 3+ 条
[ ] 与其他文档的交叉引用双向存在(A 引 B,B 也应引 A)
[ ] 结构化日志点 ≥ 3 处
[ ] Metrics 采集点 ≥ 2 处(如果业务逻辑涉及)
[ ] 本文档所有 ADR 编号与 v3.1 方案一致
```

---

## 4. 先导文档(`DOC-CC-ONBOARDING.md`)规划

### 4.1 为什么需要这份

用户 Q4 选 (c): **DOC-00 保留愿景,新文件讲执行**。

DOC-00 回答"Prism 是什么",先导回答"Sonnet 4.6 拿到任务怎么开工"。两份目标读者、语气、结构完全不同。

### 4.2 先导文档大纲

```
# DOC-CC-ONBOARDING.md — 执行者先导

§0 如何阅读本文档
   - 每次新会话第一步读这份
   - 读完这份,再读对应 Task 所属的 DOC 文档
   - 任何时候迷茫,回到这份确认心智模型

§1 项目心智模型(3 分钟速成)
   - Prism = Manus × CC × 主权自托管
   - 4 层服务拓扑(backend / postgres / redis / nginx)
   - 5 层架构(Entrypoints / Orchestration / Harness / Agent / Infrastructure)
   - 子进程边界: Backend (Layer 1-2, Infrastructure) + 子进程 (Layer 3-5)
   - 关键协议: Redis 直通流式 + HTTP 关键事件 + Redis BLPOP 反向通信

§2 必读前置(5 份文件的阅读顺序)
   2.1 本文档 — 执行心智模型
   2.2 DOC-00 — 愿景和铁律
   2.3 DOC-01 — 系统架构(Schema / API / 服务拓扑)
   2.4 当前 Task 所属 DOC
   2.5 PROGRESS.md + DECISIONS.md — 进度和历史决策

§3 开发六原则(硬底线,不可违反)
   3.1 单一职责
   3.2 最简代码(不做向后兼容)
   3.3 类型严格(Python 完整 type hints)
   3.4 KISS
   3.5 文档置信度(绝不推测写代码)
   3.6 禁止打补丁(深度融合,严禁从根源绕过)

§4 Task 执行标准流程(9 步验收)
   [引用 DOC-00 §10.4]
   针对 Sonnet 4.6 容易犯的错列陷阱清单

§5 Skill 加载规则
   - 所有 Skill 推荐加载
   - 找不到 Skill 时的等效手动步骤
   - 前端 Task 特殊要求

§6 关键架构心法(从 CC 学到的 7 条)
   6.1 Prompt 不是文本,是 runtime assembly
   6.2 Tool 不是裸调,是治理 Pipeline
   6.3 Agent 不是万能 Worker,是专业化分工
   6.4 Fork 不是"再开一个 Agent",是上下文隔离 + 缓存共享
   6.5 Coordinator-Workers 是复杂任务的解法
   6.6 "好行为"要制度化,不能靠模型即兴发挥
   6.7 上下文是稀缺资源,要当预算管理

§7 三个参考锚点的差异化吸收
   7.1 从 Manus 学到的: 产品体验 + 双入口 + 多步骤任务拆分
   7.2 从 CC 学到的: Harness 架构 + Prompt 装配 + Skills/Hook/MCP 生态
   7.3 主权工具的底线: 4C8G 跑得起来 + Docker Compose + 开箱 Grafana

§8 常见陷阱与反模式
   8.1 回调风暴(不要每个 token 发 HTTP,用 Redis pub)
   8.2 Compaction 破坏 tool_use↔tool_result 配对
   8.3 工具调用串行化(要 asyncio.gather)
   8.4 SSE JWT 走 URL query(要 ticket)
   8.5 每个服务一个 Harness 实例(只在子进程一份)
   8.6 sequence_no 用 max+1(并发冲突,要 DB 序列)
   8.7 JWT_SECRET 当 ENCRYPTION_KEY 用
   8.8 ask 权限用轮询(要 Redis BLPOP)
   8.9 Fork 子 Agent 覆盖 model(Cache miss)
   8.10 PluginBuilder 硬编码 5 轮(要完整度打分)

§9 断点恢复协议
   - 会话挂了如何续
   - PROGRESS.md 和 Git 的关系
   - 子进程崩溃后的恢复

§10 质量自检 Checklist
   [引用本 master review §3.4]

§11 你(Sonnet 4.6)的工作边界
   - 你可以: 按 PRD 精确实现,发现设计错误时暂停询问
   - 你不可以: 擅自变更 PRD 的架构决策,跳过 Skill 加载,打补丁绕过问题
   - 遇到冲突时: 1) 查 DECISIONS.md 是否有相关 ADR 2) 没有则暂停询问用户

§12 CC 源码关键文件索引
   [引用 PDF §10]
   改写 PRD 时精确引用

§13 三层质量保证
   Layer 1: Prompt 层(PromptAssembler 静态约束 + 动态约束)
   Layer 2: Harness 层(Middleware / Hook / Guardrail / Permission)
   Layer 3: 测试层(pytest + Playwright + CI)
```

### 4.3 先导文档的篇幅预期

约 6000-8000 字,Sonnet 4.6 应该 5 分钟读完,读完后知道:
- 项目是什么 / 架构长啥样
- 拿到 Task 先做什么 / 后做什么
- 什么能做 / 什么不能做
- 遇到问题去哪里查

---

## 5. 13 份 PRD 改写大致规模预估

| 文档 | 当前规模 | 预计改写后 | 增长原因 |
|---|---:|---:|---|
| DOC-00 | 44KB | 55KB | §10 补强 + 增加术语表 + 参考资料索引 |
| DOC-01 | 50KB | 80KB | Schema 从 14 张扩到 19 张 + 所有新协议的契约定义 |
| DOC-02 | 50KB | 75KB | Prompt Section 粒度对齐 CC + TokenEstimator 精确化 + Provider capability matrix |
| DOC-03 | 80KB | 130KB | permission ask 协议 + Hook 完整字段 + Compaction 配对算法 + Middleware 4 钩点 |
| DOC-04 | 56KB | 100KB | Verifier 完整 prompt + Fork Briefing + agent-scoped MCP + Task 4.5 修订 |
| DOC-05 | 63KB | 95KB | Runtime 变量 + Skills Market 修订 + CC 兼容层 ConversionReport |
| DOC-06 | 27KB | 35KB | 三密钥启动校验 + audit 扩展 |
| DOC-07 | 48KB | 85KB | sequence_no 原子性 + 子进程恢复 + coordinator 恢复 + SSE ticket + permission-answer |
| DOC-08 | 24KB | 40KB | 幂等性 + 群聊 binding + 告警通道 |
| DOC-09 | 17KB | 45KB | Task 9.3 Part B 完整 + skill_installs / providers scope |
| DOC-10 | 9KB | 50KB | SSE Client 完整状态机 + API Client 完整 + 错误处理 |
| DOC-11 | 25KB | 70KB | 所有 Task Part B 扩充 + 新增 Task 11.6(Admin Obs 面板) |
| DOC-12 | 28KB | 80KB | 从 3 Task 扩到 7 Task + Grafana Dashboard JSON + 告警通道 |
| **新: DOC-CC-ONBOARDING** | — | 25KB | 新增先导文档 |
| **总计** | **521KB** | **965KB** | 近翻倍 |

**964KB 约 24 万字**。对于一个要 Production-grade 直接编码执行的 PRD 体系,这是合理密度。

---

## 6. 关键风险和权衡

### 6.1 工作量风险

14 份文档 × 平均 70KB = 将近 1MB 的 Markdown 输出。单 session 的 context 装不下,必须分多次会话或分批落盘。

**缓解**:
- 每份 PRD 写完立即落盘 `/mnt/user-data/outputs/`
- 每阶段(B.1 / B.2 / B.3 / B.4 / B.5)结束后给用户 present_files
- 会话断了能从 outputs 续

### 6.2 一致性风险

跨 14 份文档的编号、API 路由、Schema 字段一致性,是真实挑战。改动一处,经常要联动改 3-5 处。

**缓解**:
- 阶段 C 的"跨文档一致性检查"是硬门
- 维护一份 `cross-references.md`(隐式)记录所有交叉引用
- 最后交付时给一份 `changes-checklist.md` 列出所有 115 个修改点的落地状态

### 6.3 CC fidelity 风险

我对 CC 的理解依赖 PDF,但 PDF 也是二手研究。某些 CC 细节(比如 permission 的 6 种模式具体是什么、AgentTool 的内部 state 管理)PDF 没展开,我可能会凭推理写。

**缓解**:
- 涉及 CC 具体机制时,引用 PDF 章节号(比如"参考 PDF §6.3 fork path 描述")
- 无法确证的细节,显式标注 `> ⚠️ 基于 PDF 推断,建议实现时查阅源码验证`
- 关键卡点,用户可以临时贴 CC 源码片段补强

### 6.4 4.6 降智风险

用户明确说: "文档的第一版是由 sonnet4.6 进行 coding"。

Sonnet 4.6 的盲区(从 v3.1 AUDIT 推断):
- 实现级 bug 检测能力在线,架构级问题盲视
- 长 Task 中容易漏掉前置条件
- Skill 加载指令可能跳过
- Playwright E2E 容易只跑主 happy path,不测边界

**缓解**: 每份 PRD 加 **§陷阱清单**,专门列"4.6 容易犯的错",改写时显式标注。

---

## 7. 最终交付物清单

改写阶段结束后,给用户的交付物:

### 必交付(核心)
1. **13 份重写后的 PRD**: DOC-00 ~ DOC-12
2. **新增先导文档**: DOC-CC-ONBOARDING.md
3. **`changes-checklist.md`**: 115 个修改点的落地状态表

### 辅助交付
4. **`cross-references.md`**: 跨文档引用清单(可选,但建议)
5. **`adr-index.md`**: 所有 ADR 编号的汇总索引(v3.1 重编号后)
6. **`api-routes-index.md`**: 所有 API 路由的汇总清单

### 历史保留(已完成)
7. `user-preferences-archive.md`
8. `review-patch-pdf.md`
9. `review-batch1-v2.md`
10. `review-batch2.md`
11. `review-batch3.md`
12. `review-batch4.md`
13. `review-batch5.md`
14. `review-master.md`(本文档)

---

## 8. 下一步建议

### 8.1 用户动作

在进入改写阶段前,建议你:

1. **审阅 Batch 5 和本 master review**,确认方向
2. **确认 P0 / P1 优先级分档合理**
3. **确认先导文档(§4.2)大纲方向**,有无要加的内容
4. **确认改写节奏**(§3.1 的阶段 A→B→C),有无调整

### 8.2 如果全部确认,我的下一步

1. 起草 **DOC-CC-ONBOARDING.md** 给你 review
2. 你确认后,开始阶段 B.1: 改写 DOC-00 / DOC-01 / DOC-02

### 8.3 如果改写过程中发现新问题

- 小问题: 就地修,并在 `changes-checklist.md` 补记录
- 大问题: 暂停,写 patch 文件提醒你决策(和 Batch 1 v2 / PDF 补丁一样)

---

## 9. 一句话收尾

**Review 阶段结束。** 17 份文档、PDF 报告、历史对话全部挖透。发现 115 个修改点、8 个跨 Batch 一致性空洞、14 份改写规划清晰。

质量优先立场下,接下来的改写阶段工作量大、密度高、跨文档协作复杂,但每一步都有明确的 checklist 支撑。

**接下来的动作**: 起草先导文档 → 13 份 PRD 逐份改写 → 最终校验 → 交付。

---

> **附录 A**: Review 阶段所有文件索引
> ```
> /mnt/user-data/outputs/
>   ├── user-preferences-archive.md    — 用户历史要求归档
>   ├── review-patch-pdf.md            — CC PDF 对照补丁
>   ├── review-batch1.md               — Batch 1 v1(已被 v2 覆盖,保留历史)
>   ├── review-batch1-v2.md            — Batch 1 v2: 总纲层
>   ├── review-batch2.md               — Batch 2: Agent 核心层
>   ├── review-batch3.md               — Batch 3: Backend 层
>   ├── review-batch4.md               — Batch 4: Frontend 层
>   ├── review-batch5.md               — Batch 5: Observability & Entropy
>   └── review-master.md               — 本文档
> ```

> **附录 B**: 即将生成的文件预览
> ```
> 阶段 A 交付:
>   DOC-CC-ONBOARDING.md  (~25KB)
> 
> 阶段 B 交付:
>   DOC-00-v4.md / DOC-01-v4.md / DOC-02-v4.md
>   DOC-03-v4.md / DOC-04-v4.md / DOC-05-v4.md
>   DOC-06-v4.md / DOC-07-v4.md / DOC-08-v4.md / DOC-09-v4.md
>   DOC-10-v4.md / DOC-11-v4.md / DOC-12-v4.md
> 
> 阶段 C 交付:
>   changes-checklist.md / cross-references.md / adr-index.md / api-routes-index.md
> ```
