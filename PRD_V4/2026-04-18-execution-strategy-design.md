# Prism v2 PRD v4 实施执行策略

> **文档类型**: 执行策略 design doc
> **日期**: 2026-04-18
> **适用范围**: DOC-00~12 v4 共 14 份 PRD,51+ Task 的完整实施阶段
> **相关文档**: DOC-CC-ONBOARDING.md(Sonnet 先导)/ HANDOFF-to-ClaudeCode-DOC-03-to-12.md(改写指令,已完成)

---

## 1. 背景与核心约束

### 1.1 已有资源

- 14 份 v4 PRD,合计约 16,000 行,每份含 Part A(设计 + ADR)+ Part B(Sonnet 可零猜测执行的 prompt + 验证步骤)
- 累计 120 个 ADR(ADR-001 ~ ADR-120),决策脉络完整
- DOC-CC-ONBOARDING 先导文档(心智模型 / 六原则 / 10 条陷阱 / 自检 Checklist)

### 1.2 执行者组合

- **主执行**:Sonnet 4.6(在本地 Claude Code session 中实施代码)
- **顾问**:Opus 4.7(通过 `/advisor` 斜杠命令常驻,全程可观察 Sonnet)
- **方法论**:superpowers skills(TDD / verification-before-completion / systematic-debugging 等)
- **PR 自修复**:`/autofix-pr`(远程 Claude Code session,监控 PR 的 CI / review bot 反馈并自动修复)

### 1.3 核心挑战

- 51+ Task 全串行执行慢,全并行则依赖失控
- Sonnet 1M context 足够单 Task 但跨 Task 必须断 session
- PR 粒度过细(Task 级)会 review 疲劳,过粗(Phase 级)单 PR 太大 /autofix-pr 失效
- advisor 一直在线若频繁介入会让 Sonnet 僵化,完全沉默又失去兜底意义

---

## 2. 执行架构

### 2.1 粒度决策(三个维度)

| 维度 | 粒度 | 数量 | 理由 |
|---|---|---|---|
| **会话** | 1 Task = 1 Sonnet session | ~51 session | Task 是 PRD 原子单元(Part A/B 已围绕它组织);单 Task 实施约 100-300k tokens,1M 绰绰有余;跨 Task 开新 session 避免上下文污染 |
| **Commit** | Task 完成后 commit 到同一 branch | 每 DOC 一条 branch | DOC 内 Task 耦合紧,同 branch 渐进 commit |
| **PR** | 1 DOC = 1 PR | 14 个 PR | Task 级太碎(merge 冲突多),Phase 级太大(/autofix-pr 跑不动),DOC 级是甜蜜点 |

### 2.2 整体流程

```
┌─ 按 DOC 依赖顺序挑选下一个 DOC(见 §3)────────────┐
│                                                    │
│   创建 branch: feat/doc-XX-v4                     │
│   ↓                                                │
│   ┌─ Task N 循环 ──────────────────────────────┐ │
│   │  1. 新 Sonnet session 启动                 │ │
│   │  2. /advisor 常驻(Opus 观察)              │ │
│   │  3. Sonnet 读:                             │ │
│   │     - 该 Task Part A/B                      │ │
│   │     - PROGRESS.md / DECISIONS.md /         │ │
│   │       HANDOFF-LOG.md                        │ │
│   │     - CLAUDE.md 硬底线                      │ │
│   │  4. Sonnet:TDD 写测试 → 实现 → 验证         │ │
│   │  5. 验证通过:commit 到 branch               │ │
│   │     - 更新 PROGRESS.md(commit hash)        │ │
│   │     - 追加 DECISIONS.md(ADR 实施备注)     │ │
│   │     - 写 HANDOFF-LOG.md 尾记               │ │
│   │  6. session 结束                            │ │
│   └─ 下一个 Task ──────────────────────────────┘ │
│                                                    │
│   DOC 所有 Task 完成 → 开 PR                      │
│   ↓                                                │
│   /autofix-pr 远程监控 PR:                         │
│   - CI / lint / format / test 失败 → 自动修       │
│   - review bot 评论 → 自动响应                    │
│   - retry ≤ 3 次                                   │
│   ↓                                                │
│   人工 review(对照 DOC 的 ADR 和验收标准)→ merge │
└────────────────────────────────────────────────────┘
```

---

## 3. DOC 依赖顺序(关键路径)

已完成:DOC-00 / DOC-01 / DOC-02 v4(已在 Claude Web 做完)

实施顺序(按依赖图):

```
Phase 1(Agent 核心):
  DOC-03(Harness Core) — 6 Task
    ↓
  DOC-04(Agent Orchestration) — 5 Task(依赖 DOC-03 的 Harness)
    ↓
  DOC-05(Plugin Ecosystem) — 7 Task(依赖 DOC-03 + DOC-04)

Phase 2(Backend 模块):
  DOC-06(Auth & User) — 2 Task(独立)
    ↓
  DOC-07(Session-Run-Task) — 4 Task(依赖 DOC-06)
    ↓
  DOC-08(IM Gateway) — 3 Task(依赖 DOC-07)
  DOC-09(MCP/Provider/Admin) — 3 Task(依赖 DOC-06,可与 DOC-08 并行)

Phase 3(前端):
  DOC-10(Frontend Foundation) — 4 Task(依赖 DOC-06~09 API)
    ↓
  DOC-11(Frontend Features) — 6 Task(依赖 DOC-10)

Phase 4(运维封装):
  DOC-12(Observability) — 8 Task(依赖 DOC-03/07,可在 Phase 2 后开始)
```

**并行空间**:DOC-08 和 DOC-09 可并行(两条独立 branch + 两个 Sonnet session);DOC-12 Task 12.4~12.8 可在 Phase 2 完成后与 Phase 3 并行。

---

## 4. 上下文延续(跨 session 四件套)

### 4.1 `PROGRESS.md`(项目根)

Task 状态表,每行:
```
| Task | Status | Started | Completed | Commit | Session Notes |
|---|---|---|---|---|---|
| DOC-03 Task 3.1 | completed | 2026-04-18 | 2026-04-18 | a3f2b1c | 心跳 writer + Redis 直通如期落地 |
| DOC-03 Task 3.2 | in_progress | 2026-04-19 | - | - | Middleware 4 钩点,正在补 pre_tool_use 集成 |
```

### 4.2 `DECISIONS.md`(项目根)

120 个 ADR 落地台账。每个 ADR 完成时追加:
```
## ADR-020: Harness 单实例(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03
- **实施状态**: ✅ 2026-04-18
- **落地位置**: executor/__main__.py + executor/harness/lifecycle.py
- **偏离点**: 无 / 或"因 X 原因微调为 Y,见 commit a3f2b1c"
```

### 4.3 `CLAUDE.md`(项目根,精简版)

~150 行内:
- 项目心智模型 3 分钟速成(抄 DOC-CC-ONBOARDING §1)
- 六原则硬底线(抄 §3)
- 10 条陷阱(抄 §8)
- 指向完整文档的链接

### 4.4 `HANDOFF-LOG.md`(项目根)

每个 Sonnet session 结尾必写的 200-400 字记录:
```
## 2026-04-19 14:30 — Task 3.2 完成
### 做了什么
- 实现 middleware 4 钩点基类
- 注入到 QueryEngine._execute_single_tool
- 所有验证步骤 PASS(含 4 钩点分别触发断言)

### 下一个 Task(3.3)需要注意
- Hook decision 11 字段合并规则要特别看 merge_decisions() 的 updated_input 冲突处理,别退让
- ask_protocol.py 的 Redis key 格式是 perm_answer:{uuid},Backend 端必须匹配

### 遗留风险
- 无
```

---

## 5. /advisor 介入规则

### 5.1 默认沉默原则

Opus 在 /advisor 模式下默认只观察不打断。过度介入会让 Sonnet 变得过度保守,反而降低速度。

### 5.2 三条介入红线

Opus 在以下任一情况发生时**必须打断并发声**:

1. **违反 DOC-CC-ONBOARDING §3 六原则**
   - 混用 JWT_SECRET / ENCRYPTION_KEY / CALLBACK_SECRET
   - 按 message index 裁剪(破坏 tool_use↔tool_result 配对)
   - sequence_no 用 `COALESCE(MAX,0)+1` 无锁方案
   - 改了 PRD 文档本身(PRD 是不可变合同)

2. **超出本 Task 范围的删除/重构**
   - 删除其他 Task 的代码
   - 重构其他 Task 的文件超过 10 行
   - 修改 Schema 表结构未跑 alembic revision

3. **验证失败升级阶梯**
   - 第 1 次失败:Sonnet 自己 debug(用 systematic-debugging skill)
   - 第 2 次失败:Opus advisor 介入诊断(可能 PRD 写错 / 可能理解偏差)
   - 第 3 次失败:中断 session,人工介入(见 §8.1)

### 5.3 建议模式(非打断)

其他情况下 Opus 可以发"建议 tag"(类似 code review 的 nit),Sonnet 可选择采纳或忽略,不必回复。

---

## 6. Superpowers skills 角色分配

Superpowers 是方法论框架,不是工具。它规定了 Sonnet "怎么做"一个 Task,和 advisor(审)/ autofix-pr(修)分工互不重叠:advisor 管"方向对不对",autofix-pr 管"PR 合不合得进",**superpowers 管"每一步怎么走"**。

### 6.1 总是加载(启动钩)

- **`superpowers:using-superpowers`** — 每个 Sonnet session 开头必加载,建立 skill 使用心智;CLAUDE.md 也引用它作为硬底线

### 6.2 Task 级(rigid,必须按流程走)

**关键理解**:PRD v4 每个 Task 的 Part B 本身就是完整实施 plan(上下文 / 前置条件 / 文件树 / 实现规范精确到函数签名 / 验证步骤含期望输出 / 完成后动作)。**Sonnet 直接按 Part B 开工,不需要再用 writing-plans 重写一份 plan**。writing-plans 在本项目内的角色被 PRD 吃掉了。

按 Task 生命周期顺序使用:

| 阶段 | Skill | 作用 |
|---|---|---|
| Task 启动 | ~~`superpowers:writing-plans`~~(不用) | Part B 已是 plan。仅当 Part B 内部有执行顺序歧义时,在 HANDOFF-LOG 写 50-100 字备忘,不生成独立 plan 文件 |
| 写代码前 | `superpowers:test-driven-development` | 先写失败测试,再写实现;用 Part B 的验证步骤断言作为测试初稿 |
| 遇到 bug | `superpowers:systematic-debugging` | 验证失败第 1 次时用;配合 structlog 日志和 OTel trace 定位 |
| Claim 完成前 | `superpowers:verification-before-completion` | 必须跑,不能跳;对照 §9 十项质量门 |
| Task 完成后 | `superpowers:requesting-code-review` | 调 code-reviewer agent 对本 Task 做独立审查(看 ADR 符合度 + 测试完整性) |

### 6.3 DOC 级(rigid)

- **`superpowers:finishing-a-development-branch`** — DOC 所有 Task 完成后,开 PR 前触发;skill 会引导选择 merge / PR / cleanup 路径

### 6.4 按需使用(flexible)

| 场景 | Skill | 触发条件 |
|---|---|---|
| 并行 DOC(如 DOC-08 + DOC-09) | `superpowers:using-git-worktrees` | 两条独立 branch 同时推进时,用 worktree 隔离 |
| DOC 内 Task 独立可并行 | `superpowers:dispatching-parallel-agents` | DOC-12 Task 12.4/12.5/12.6/12.7 之间无依赖,可分派 |
| 整个 DOC 一次性规划 | `superpowers:executing-plans` | DOC 开工时把该 DOC 的 N 个 Task Part B 视为 N 个 checkpoint,按顺序推进,不额外生成 plan 文件 |
| 收到 review bot 反馈 | `superpowers:receiving-code-review` | /autofix-pr 无法处理的 review 评论,Sonnet 介入时用 |

### 6.5 禁止使用(YAGNI)

以下 skill 在 Prism v2 实施阶段**不用**:

- `superpowers:brainstorming` — 只在元策略阶段(如本文档的撰写过程)用。具体 Task 的 brainstorming 已在 PRD Part A 完成
- `superpowers:writing-skills` — 本项目不创建新的 superpowers skill

### 6.6 Skill 冲突决议

superpowers skill 的某条要求和 PRD 的某条 ADR 冲突时:

1. 首先按 DOC-CC-ONBOARDING §0 的优先级:**用户 CLAUDE.md > superpowers > 系统默认**
2. PRD v4 是用户合同,等同于 CLAUDE.md 级别
3. 所以 PRD 的 ADR 优先于 superpowers 的 rigid 要求

举例:某 skill 要求"任何情况都必须 TDD",但 PRD 的某个 Task 是"补充一个只读 GET 端点",强行 TDD 会让 Sonnet 先写 mock 测试。这时 PRD 的"最小实现"精神优先,Sonnet 可以跳 TDD。

---

## 7. /autofix-pr 边界

### 7.1 允许自动修复

- CI 失败:lint / format / type-check / 测试
- 依赖冲突(package.json / requirements.txt 合并)
- import 顺序 / 未使用 import
- trailing whitespace / LF 结尾

### 7.2 禁止自动修复

- ADR 级设计改动(任何涉及 ADR 文字的修改)
- 新增 / 删除文件(除 format 自动生成的)
- Schema 修改(alembic revision)
- secret 相关代码
- 跨 DOC 的 refactor

### 7.3 失败策略

- retry 上限 3 次
- 超过 3 次或触碰禁止区域 → 停下并在 PR 上 @ 人工
- /autofix-pr 每次 commit 都要有 `[autofix]` 前缀,便于审计

---

## 8. 常见场景 SOP

### 8.1 Task 验证挂了怎么办

1. Sonnet 读错误日志,自己 debug(第 1 次尝试)
2. 失败 → Opus /advisor 介入(三条红线第 3 条)
3. 定位根因:
   - **代码 bug** → Sonnet 修
   - **PRD 歧义/错误** → 写 blocker.md,**停下等人工**,不要自行改 PRD
   - **前置 Task 未完成** → 回退到 PROGRESS.md 检查
4. 超过 3 次 → 中断,人工介入

### 8.2 跨 DOC 发现冲突怎么办

举例:做 DOC-07 Task 7.3 发现 DOC-06 v4 ADR-051 的 SSE ticket 生成逻辑有漏洞 →

- **不修 DOC-06**:PRD 是合同
- **不在 DOC-07 绕过**:这会让 DOC-06 的测试失效
- **正确做法**:写 blocker.md,明确 "DOC-06 v4 §X.Y 段 的 Z 字段存在问题",停下等人工裁定

### 8.3 /autofix-pr 和 advisor 冲突怎么办

- advisor(本地,实时)vs /autofix-pr(远程,异步)角色不重叠:前者管实施,后者管 PR 后处理
- 两者都改同一文件 → 以 advisor 签字的 commit 为准(advisor 代表设计权威)
- /autofix-pr 提交必须有 `[autofix]` 前缀,advisor 介入的提交无前缀

---

## 9. 质量门

Task 不算完成,除非:

1. ✅ Part B 所有文件创建完毕
2. ✅ Part B 验证步骤全部 PASS(不能 skip)
3. ✅ 没有 `...` 省略号(Python Ellipsis 除外)/ `TODO:` / `FIXME:`
4. ✅ 关键路径有 structlog 日志(事件名 `{domain}.{action}`)
5. ✅ 业务指标有 Prometheus counter + histogram(对照 DOC-12 v4 Task 12.4)
6. ✅ 跨进程操作有 OTel span(对照 DOC-12 v4 Task 12.5)
7. ✅ secret 用对 key(三密钥独立)
8. ✅ Schema 改动跑了 alembic revision + upgrade
9. ✅ PROGRESS.md / DECISIONS.md / HANDOFF-LOG.md 都已更新
10. ✅ git commit message 按 conventional commits(feat/fix/chore/docs)

DOC 不算完成,除非:

- ✅ 该 DOC 所有 Task 的 10 项质量门都通过
- ✅ DOC 级集成测试 PASS(跨 Task 协同,如 DOC-07 的 SSE + callback + promote 端到端)
- ✅ PR 开出后 /autofix-pr 通过 CI
- ✅ 人工 review 对照 PRD 的 ADR 和验收标准

---

## 10. 风险与回退

### 10.1 主要风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 某 DOC 的 PR 在 /autofix-pr 后仍无法合入 | 中 | 高 | 人工介入;必要时拆成多个 PR |
| 跨 DOC 发现 ADR 冲突 | 低 | 高 | 停下写 blocker,用户修 PRD |
| Sonnet session 消耗的 token 超预期 | 中 | 中 | 预留每 Task 500k budget,超 → 拆 Task 成子 Task |
| Opus /advisor 介入频率过高拖慢 Sonnet | 中 | 中 | 三条红线严格执行,其他建议模式 |
| PROGRESS.md 过时导致下个 session 对状态理解错 | 低 | 高 | 强制每 session 结束写 HANDOFF-LOG;开新 session 第一步必读最近 3 条 log |

### 10.2 Phase 级回退策略

某 Phase 发生重大设计错误(如 DOC-03 Harness 实现完发现 TAOR 循环有根本 bug)→

1. 在对应 PR 上标记 `need-redesign`
2. 回退该 Phase 的所有 merge(revert commits)
3. 修 PRD(需要用户授权)
4. 重新实施该 Phase

---

## 11. 启动前 TODO

开始实施前,用户/Sonnet 需要先准备:

- [ ] 在项目根创建 `CLAUDE.md`(精简版,从 DOC-CC-ONBOARDING 抄)
- [ ] 在项目根创建空的 `PROGRESS.md` / `DECISIONS.md` / `HANDOFF-LOG.md`(含表头模板)
- [ ] 初始化 git 仓库 + 设置 branch protection(main 禁止直推,必须 PR merge)
- [ ] 配置 `/advisor` 常驻(Opus 4.7)
- [ ] 配置 `/autofix-pr` 权限(只能 push 到非 main branch;只能 commit 带 `[autofix]` 前缀)
- [ ] Sonnet 第一次 session 前,通读 DOC-CC-ONBOARDING + DOC-00 v4 + DOC-01 v4 + DOC-02 v4
- [ ] 跑通一次 hello-world Task(建议用 DOC-03 Task 3.1 作为"仪式性起步",确认全链路畅通)

---

## 12. 核心哲学(一句话)

**Sonnet 主导执行,Opus/autofix 兜底;Task 级断会话,DOC 级开 PR;PRD 是不可变合同,发现问题写 blocker 而非自修。**

---

> **本文档版本**: 1.0
> **下一步**: 用户 review → 无异议则按 writing-plans skill 生成首批 Task 的详细实施计划(可选:或直接按 DOC-03 Task 3.1 开第一个 session 试跑)
