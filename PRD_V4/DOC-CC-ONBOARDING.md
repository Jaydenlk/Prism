# DOC-CC-ONBOARDING — Claude Code(Sonnet 4.6)执行 PRD v4 前的必读先导文档

> **文档编号**: DOC-CC-ONBOARDING
> **版本**: 1.0
> **日期**: 2026-04-18
> **性质**: 先导文档 — 给下一个执行者(Sonnet 4.6)的心智模型 / 阅读路线 / 硬底线 / 陷阱清单
> **读者**: Claude Code(Sonnet 4.6),即将按 DOC-00 ~ DOC-12 v4 实施 Prism v2
> **阅读时长**: 15-20 分钟
> **来源**: Master review §4.2 大纲 + review-patch-pdf.md 附录 + user-preferences-archive.md 14 条硬要求

---

## §0 如何阅读本文档

- 这不是 PRD,是给你的 "地图 + 操作手册"。
- **第一次读**:按顺序一遍读完,标红的部分再读一次
- **每次动工前**:重看 §3(六原则)+ §8(陷阱清单)+ §10(自检 Checklist)
- **Task 执行中卡壳**:回到 §9(断点恢复)

不要跳过 §2(必读前置)直接去看代码骨架。你需要先建立心智模型,才能正确理解 PRD。

---

## §1 项目心智模型(3 分钟速成)

**Prism v2 是什么**:一个自托管的 AI Agent 编排平台。用户通过 Web 或 IM(飞书/企微/Telegram)提问,Agent 在后端的子进程中以 TAOR 循环(Think → Act → Observe → Respond)跑完任务并流式返回结果。

**和 Prism v1 的关键差异**:v1 把能力外包给 `claude_agent_sdk`,v2 **自研** Harness Runtime + Agent Engine。这意味着循环控制、工具治理、上下文压缩都在我们手里。

**三个关键抽象**:
1. **Provider**(DOC-02/09) — 对接外部模型(Anthropic / OpenAI / 兼容 endpoint)。统一抽象 `ModelAdapter.stream()`,底层双协议(Anthropic canonical / OpenAI 展开)
2. **Harness Runtime**(DOC-03) — TAOR 主循环 + Middleware 4 钩点 + Hook 4 handler + Permission Engine + Guardrails + Compaction 4 级。**在子进程内跑**,Backend 不持有
3. **Plugin Ecosystem**(DOC-05) — Skill(三级加载) / Hook / MCP / Plugin 四类扩展机制

**分层架构**(从下往上):
```
Layer 5  基础设施:FastAPI/Postgres/Redis/子进程模型
Layer 4  引擎核心:Prompt 装配 / 模型适配 / 工具执行
Layer 3  Harness Runtime:治理 / 权限 / 钩点 / Compaction / Memory
Layer 2  Agent 编排:6 种专业 Agent + Fork + Coordinator + TaskRouter
Layer 1  Plugin 扩展:Skill / Hook / MCP / Plugin
Layer 0  产品形态:Web + IM + CLI 入口
```

**进程边界**:Backend(FastAPI)和 Executor(子进程)是两个独立进程,通过 DB + Redis 通信。子进程崩溃不影响 Backend,Backend 崩溃不影响正在跑的子进程(Redis 中心跳和消息持久化保证)。

---

## §2 必读前置(5 份文件的阅读顺序)

**严格按顺序读完再动工**:

1. **DOC-00-v4.md**(愿景 + 四条铁律 + P1-P7 设计原则)— 30 分钟。这是"为什么"的根。
2. **DOC-01-v4.md**(系统架构 + 19 张表 Schema + API 路由总表 + Redis namespace + SSE 事件协议)— 60 分钟。Schema 是真相源,代码对齐这份。
3. **DOC-02-v4.md**(Model Adapter + Prompt Engine)— 45 分钟。理解 Provider 抽象和 Prompt 动态装配。
4. **本文档**(DOC-CC-ONBOARDING)— 15 分钟(你现在正在读)
5. 要做哪个 DOC-XX,**再读那份**。不用一次读完 13 份。

**跳读规则**:
- 如果你要做 Backend 任务 → 重点 DOC-01/06/07/08/09
- 如果你要做 Harness 任务 → 重点 DOC-02/03/04
- 如果你要做前端任务 → 重点 DOC-10/11 + UI design spec
- 如果你要做 Observability 任务 → 重点 DOC-12

**交叉引用规则**:PRD 里说 "见 DOC-XX v4 §Y.Z" 时,一定去查,不要凭记忆写代码。

---

## §3 开发六原则(硬底线,不可违反)

### 原则 1:对齐 Schema,不自作主张

数据库表有 19 张(DOC-01 v4 §4),字段、索引、约束已经定死。代码里用到的字段必须和 Schema 一致,包括:
- `messages.sequence_no` 必须走 ADR-060(per-session 序列 或 advisory_xact_lock)
- `providers.scope` 有 `platform|user` 两值
- `runs.harness_summary` 是 JSONB,schema 在 DOC-07 v4 定义
- `im_bindings` 是三元组 UNIQUE(channel, platform_user_id, platform_chat_id),不是二元组

### 原则 2:保留 99% 原文

这是**改写**不是**重写**。如果 Schema、Task 编号、Part A/B 结构、ADR 编号已经定好,你不要"顺手重构"。每一条 ADR 都有它的来源(review 的某个具体点),擅自合并或改写会丢信息。

### 原则 3:密度达标(零猜测可执行)

你写的代码骨架(Part B 实现规范)必须让**下一个 Sonnet 看完能直接开写**。
- 禁止 `...` 省略号(除非是 Python 真 literal,如 `...` 表示 Ellipsis)
- 禁止 `TODO:` 占位符
- 禁止"这部分由实施阶段补充"
- 函数签名必须精确(参数名 + 类型)
- 关键路径必须有 structlog / Prometheus / OTel 采集(见 DOC-12 v4)

### 原则 4:改 PRD 也适用"禁止打补丁"

如果你在改 DOC-X 时发现某个 review 点需要改到 review 没提的架构,**停下来写一份 blocker.md 给用户**。不要擅自扩大改动。

### 原则 5:三密钥独立不可混用

- `JWT_SECRET` — JWT HMAC 签名
- `ENCRYPTION_KEY` — Provider API Key AES-256-GCM 加密
- `CALLBACK_SECRET` — 子进程回调 HMAC

main.py 启动时用 `validate_secrets()` 校验三者互不相等。共用一个会导致轮换时所有 Provider API Key 失效或者不敢轮换 JWT。

### 原则 6:进程边界 = 信任边界

Backend 和 Executor 是两个独立进程,通信只走:
- Redis(高频 text_delta / permission_ask answer / 心跳)
- HTTP + X-Callback-Secret(关键事件回调)
- DB(持久化 + 状态流转,通过 fetch 而非共享 session)

**禁止**:
- Backend 直接 import Harness 代码跑业务
- Executor 直接查 Backend 的表(除了独立 DB session 读 Run/Provider 配置)
- 共享 Python 对象(如 settings 实例)

---

## §4 Task 执行标准流程(9 步验收)

每个 Task 按此流程执行。不要跳步:

1. **读 Task 的 Part A 全部**(含 ADR)
2. **读 Task 的 Part B 实现规范全部**
3. **读交叉引用到的所有上游 Task**(如 DOC-07 Task 7.3 引用 DOC-02 v4 Task 2.2,你先读 2.2)
4. **创建分支 / 工作目录**
5. **按 Part B 文件树创建所有文件骨架**
6. **填充实现**(遵循 Part B 给出的函数签名)
7. **跑 Part B 的验证步骤**(所有断言必须通过,不能 skip)
8. **跑 Simplify skill 审查**
9. **commit + 更新 PROGRESS.md + 更新 DECISIONS.md(记录 ADR)**

**失败处理**:
- 验证步骤挂 → 不要绕过,debug 到 pass 为止
- 发现 PRD 写错了 → 写 blocker.md 给用户,不要自行修 PRD

---

## §5 Skill 加载规则

Prism v2 自身的 Skill 系统(DOC-05 v4)不是这里说的。这里说的是 **你(Claude Code)执行 Task 时加载的 superpowers skill**。

Task Part B 的开头会说明要加载哪些 skill,典型包括:
- `superpowers:using-superpowers`(总是加载,建立心智)
- `superpowers:test-driven-development`(写测试用)
- `superpowers:verification-before-completion`(claim 完成前必跑)
- `frontend-design` / `taste-skill`(前端 Task)
- `claude-api`(涉及 Anthropic SDK 时)

**加载失败怎么办**:如果 Task 要求的 skill 找不到,立即停止并告知用户,不要"凭记忆"继续。

---

## §6 关键架构心法(从 CC 源码学到的 7 条)

### 6.1 Model-Driven Loop(TAOR 是"哑循环")

模型决定下一步做什么,Runtime 只负责执行 + 治理。不要在 Runtime 里塞"智能"(如"模型返回了工具调用,我要帮它判断这个工具用得对不对")。治理通过 Hook + Guardrails,不通过 Runtime 硬编码。

### 6.2 回调风暴是灾难(Redis 直通)

每个 token 发一次 HTTP 到 Backend 会把 Backend 搞死。方案 A(DOC-03 v4 ADR-022):text_delta / tool_use_delta 走 Redis PUBLISH,Backend SSE 订阅 forward。关键事件才走 HTTP。

### 6.3 回合组原子裁剪

Compaction 不能按 message index 裁,必须按"回合组"(一个 assistant 响应 + 配对的 tool_result)为单元。否则 tool_use ↔ tool_result 配对被破坏,下次 API 调用 400。

### 6.4 工具并行是默认

同一轮内的多个 tool_use 默认用 `asyncio.gather` 并行(DOC-03 v4 ADR-021)。串行循环 await 会让 latency 线性增长。

### 6.5 反向通信走 Redis BLPOP

permission ask 的三方协议:子进程 BLPOP 阻塞等待 → Backend 收到用户回答 RPUSH → 子进程解除阻塞。不用轮询(浪费连接),不用 WebSocket(子进程不适合开 WS server)。

### 6.6 心跳不可省

子进程启动时 asyncio.create_task 启一个 heartbeat writer,每 5s SETEX `harness:heartbeat:{run_id}` TTL=60s。Backend HeartbeatMonitor 每 10s 扫描,超 30s 标记 crashed。不这样做,子进程 OOM 或主机重启后队列永远卡住。

### 6.7 Prompt Cache 是一等公民

Anthropic prompt caching 最高节省 90% 成本。Provider capabilities 探测必须标注 `prompt_caching`,PromptAssembler 根据 capabilities 决定是否注入 cache_control。cache tokens 三字段(hit / miss / creation)必须跟踪到 runs 表,用量仪表盘突出展示。

---

## §7 三个参考锚点的差异化吸收

Prism v2 学习了三个参考项目,但不是 fork:

| 锚点 | 学什么 | 不学什么 |
|---|---|---|
| **Manus** | Skill 机制 / Plugin 架构 / 多 Agent 编排思路 | 它的 SDK 使用(我们自研)/ 它的商业 skill 源(Phase 2 再加) |
| **Claude Code(CC)** | Harness Runtime 所有细节(Hook 11 字段 / 4 handler / Compaction 4 级 / TAOR 哑循环 / sub-agent Fork) | 它的 TypeScript 栈 / 它的本地 CLI 形态 |
| **Poco(主权工具)** | 会话管理功能范围(export/import/share/fork/archive/tag/多选) | 它的 68 文件代码(体积太大,我们从零实现 <10MB) |

**冲突决议**:三个锚点对同一问题的设计冲突时,按如下顺序:
1. 优先 CC 的设计(它是 Anthropic 官方,对模型行为的理解最准)
2. 其次 Manus(抽象层更干净)
3. 最后 Poco(产品形态参考)

---

## §8 常见陷阱与反模式(10 条,对应 review-master §6.4)

| # | 陷阱 | 反模式 | 正解 |
|---|---|---|---|
| 8.1 | 回调风暴 | 每个 token 发 HTTP | Redis PUBLISH,Backend 订阅 forward(DOC-03 v4 ADR-022) |
| 8.2 | Compaction 破坏 tool_use↔tool_result 配对 | 按 index 裁剪 messages | 按回合组为原子单元裁剪(DOC-03 v4 ADR-029) |
| 8.3 | 工具调用串行化 | for 循环 await | `asyncio.gather` 并行(无依赖时,DOC-03 v4 ADR-021) |
| 8.4 | SSE JWT 走 URL query | token 泄露到日志/history/referer | 一次性 ticket(60s 过期,用后即焚,DOC-06 v4 ADR-051) |
| 8.5 | 每个服务一个 Harness 实例 | Backend + 子进程都跑 Harness | 只在子进程跑,Backend 不持有(DOC-03 v4 ADR-020) |
| 8.6 | sequence_no 用 max+1 | 并发 insert 时冲突 | PostgreSQL per-session 序列 或 advisory_xact_lock(DOC-07 v4 ADR-060) |
| 8.7 | JWT_SECRET 当 ENCRYPTION_KEY 用 | 轮换 JWT 时 Provider key 全丢 | 三密钥独立 + 启动校验(DOC-06 v4 ADR-050) |
| 8.8 | ask 权限用轮询 | 浪费连接,延迟高 | Redis BLPOP 阻塞等待(DOC-03 v4 ADR-028) |
| 8.9 | Fork 子 Agent 覆盖 model | Cache miss | Fork 3 条 prompt-level 约束强制(DOC-04 v4 ADR-034) |
| 8.10 | PluginBuilder 硬编码 5 轮 | 有人 2 轮就够了,有人 8 轮还不够 | 完整度打分动态决定(DOC-04 v4 ADR-038) |

**遇到新陷阱**:加到这份清单,更新 review-master 的相关条目。

---

## §9 断点恢复协议

你会在执行过程中遇到这些情况:

### 9.1 PRD 里的说明不够具体

- 先在代码上下文(已完成的 Task、已合入的 Schema、已定的 ADR)里找答案
- 找不到就查 review-master / batch1-5 / patch-pdf(PRD 的来源)
- 还找不到 → 写 blocker.md 给用户,**停下来**

### 9.2 PRD 和 review 冲突

- review 是 PRD v4 的来源,冲突通常意味着 v4 改写时漏了。回到 review 原文取最新结论
- 如果 review 本身内部冲突(batch 之间)→ 以 review-master 为准(master 是汇总后的最终决议)

### 9.3 实施后发现 PRD 某处不对

- 写 blocker.md,明确:位置 / 现象 / 影响面 / 建议修法
- 不要自行改 PRD(PRD 是上游合同,改了会让后续 Task 失控)

### 9.4 被打断,下次 session 接手

- 看 PROGRESS.md(哪些 Task 已完成 / in_progress 在哪一步)
- 看最近 commit message(git log)
- 看最近一次 DECISIONS.md 更新(最后落地的 ADR)
- 按 Task 执行标准流程(§4)的步骤号继续

---

## §10 质量自检 Checklist(claim 完成前必跑)

每个 Task 完成后,claim "完成" 之前,逐条过一遍:

- [ ] Part B 的所有文件都创建了,没有"下次补"
- [ ] 每个 Part A 的 ADR 都在代码里有对应实现(或明确标注为 Phase 2 占位)
- [ ] Part B 的"验证步骤"全部跑过,所有断言 PASS
- [ ] 没有 `...` 省略号(真正的 Ellipsis 除外) / `TODO:` / `FIXME:`
- [ ] 关键路径有 structlog 日志(事件名 `{domain}.{action}`)
- [ ] 业务关键指标有 Prometheus counter + histogram(见 DOC-12 v4 Task 12.4 清单)
- [ ] 跨进程操作有 OTel trace span(见 DOC-12 v4 Task 12.5)
- [ ] 涉及 secret 的地方用对了 key(JWT_SECRET / ENCRYPTION_KEY / CALLBACK_SECRET 不能混)
- [ ] 如果改了 Schema,跑了 alembic revision + upgrade
- [ ] PROGRESS.md + DECISIONS.md 都已更新
- [ ] git commit message 按 conventional commits 格式(feat/fix/chore/docs)

对齐完整版参考 review-master §3.4。

---

## §11 你(Sonnet 4.6)的工作边界

**你可以自主做**:
- 按 PRD 实现代码
- 写测试(TDD skill)
- 修自己代码的 bug
- 更新 PROGRESS.md 和 DECISIONS.md
- 跑验证步骤,合格后 commit

**你必须问用户**:
- 发现 PRD 写错了(写 blocker.md)
- 需要删除 / 降级现有功能(不是本 Task 的改动)
- 需要新增 Phase 1 未规划的能力
- 发现两个 ADR 互相矛盾无法共存

**你不可以做**:
- 修改 PRD 文档本身(除非用户明确授权)
- 删除或跳过验证步骤
- 用 `--no-verify` 跳 hook
- 把 secret 写到 .env 之外的任何位置

---

## §12 CC 源码关键文件索引

执行 Harness 相关 Task(DOC-03/04/05)时,对照 CC 源码会让你少踩很多坑。以下 11 个关键文件是优先参考对象(出处:review-patch-pdf.md 附录):

| # | CC 文件 | Prism 对应 | 什么场景看 |
|---|---|---|---|
| 1 | `src/services/query.ts` | DOC-03 v4 Task 3.1 QueryEngine | 实现 TAOR 主循环时 |
| 2 | `src/services/tools/toolHooks.ts` | DOC-03 v4 Task 3.3 HookDecision | 实现 Hook 11 字段和合并规则时 |
| 3 | `src/services/tools/runTools.ts` | DOC-03 v4 Task 3.1 `_execute_tools` | 工具并行 gather 参考 |
| 4 | `src/tools/AgentTool/built-in/verificationAgent.ts` | DOC-04 v4 Task 4.1 Verifier | 写 VERDICT prompt 时 |
| 5 | `src/services/compaction.ts` | DOC-03 v4 Task 3.5 Compaction | 4 级 Compaction 实现时 |
| 6 | `src/services/memory/*.ts` | DOC-03 v4 Task 3.5 Memory | 6 层 Memory 框架参考 |
| 7 | `src/services/skills/*.ts` | DOC-05 v4 Task 5.1 SkillLoader | 三级加载 + is_skill_context 标记 |
| 8 | `src/services/mcp/*.ts` | DOC-05 v4 Task 5.2 MCPClient | MCP 工具发现 + instructions 注入 |
| 9 | `src/services/sub_agent/*.ts` | DOC-04 v4 Task 4.2 Fork | Fork capability 白名单参考 |
| 10 | `src/services/coordinator/*.ts` | DOC-04 v4 Task 4.3 Coordinator | Plan checkpoint 参考 |
| 11 | `src/services/permissions/*.ts` | DOC-03 v4 Task 3.3 PermissionEngine | ask Redis BLPOP 协议参考 |

**注**:CC 的 TypeScript 实现和 Prism 的 Python 实现有差异,参考是"拿架构思路",不是"逐行翻译"。Python 的 asyncio / dataclass / Pydantic 有更干净的写法,别硬搬 TypeScript 的 Promise 链。

---

## §13 三层质量保证

Prism v2 的质量保证分三层,每层独立触发:

### 层 1:实施期(你自己)

- TDD:先写测试再写实现(superpowers:test-driven-development)
- 实施完跑 Part B 验证步骤
- Simplify skill 自审

### 层 2:Review 期(code-reviewer agent)

每个 DOC 的 Task 块完成后,用 `superpowers:requesting-code-review` 请求 code-reviewer 独立审查:
- 对照 Part A 的 ADR 检查设计符合性
- 对照 Part B 的验证步骤检查完整性
- 发现问题 → review 报告 → 修复 → 重新 review

### 层 3:集成期(用户验收)

- 用户对照 PROGRESS.md + DECISIONS.md + git log 做最终验收
- 发现问题由你修复后,用户重新验收

**三层都通过**,一个 Task 才算真正完成。

---

## 结束语

这份文档的目标:让你(Sonnet 4.6)在接手 Prism v2 实施任务时,**不猜测、不漏步、不越界**。

如果你看完这份文档有任何疑问,在开始动工之前提出来。PRD 已经被 Opus 4.7 和 3 个 review agent 审查过多轮,但它仍然可能有漏洞。你发现的漏洞对后续实施者也有价值,请写 blocker.md 共享。

祝你开工顺利。Prism v2 的用户(最终会被你的代码服务的人)在等你。

---

> **本文档版本**: 1.0
> **来源**: review-master §4.2 大纲 / review-patch-pdf.md 附录 / user-preferences-archive.md / Claude Opus 4.7 Web 编写
> **预计 Sonnet 4.6 阅读时长**: 15-20 分钟
> **下一步**: 按 DOC-00 v4 顺序阅读,执行 Task 时遵循本文档 §4 标准流程
