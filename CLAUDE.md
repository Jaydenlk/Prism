# Prism v2 — Claude Code 项目指引

> **适用**: 本仓库所有 Sonnet 4.6 会话
> **版本**: 1.0(2026-04-18 初始化)
> **完整版**: `PRD_V4/DOC-CC-ONBOARDING.md`
> **执行策略**: `PRD_V4/2026-04-18-execution-strategy-design.md`

---

## 心智模型(30 秒速成)

Prism v2 = 自托管 AI Agent 编排平台。用户从 Web / IM 提问,Agent 在 Backend 的子进程中跑 TAOR(Think→Act→Observe→Respond)循环,流式返回。

**分层**:Layer 5 基础设施 → Layer 4 引擎核心 → Layer 3 Harness Runtime → Layer 2 Agent 编排 → Layer 1 Plugin 扩展 → Layer 0 Web/IM/CLI 入口。

**进程边界 = 信任边界**:Backend(FastAPI)和 Executor(子进程)独立进程,通过 Redis(高频)+ HTTP with CALLBACK_SECRET(关键事件)+ DB 通信。

---

## 六原则(硬底线)

1. **对齐 Schema** — 19 张表字段已定死(见 DOC-01 v4 §4),代码不自造字段
2. **99% 原文保留** — 改 PRD 需授权;ADR 按来源落地,不顺手重构
3. **密度达标** — 禁 `...` 省略 / `TODO:` 占位 / "下次补"
4. **禁止打补丁** — 发现超出 Task 范围的改动,写 `blocker.md` 停下
5. **三密钥独立** — `JWT_SECRET` / `ENCRYPTION_KEY` / `CALLBACK_SECRET` 不可混用,启动校验
6. **进程边界 = 信任边界** — Backend 不 import Harness 跑业务;Executor 不共享 Python 对象

---

## 10 条陷阱(对照 DOC-CC-ONBOARDING §8)

| # | 陷阱 | 正解(查对应 ADR) |
|---|---|---|
| 1 | 回调风暴(每 token 一次 HTTP) | Redis 直通 PUBLISH(ADR-022) |
| 2 | Compaction 按 index 裁破坏 tool_use↔tool_result 配对 | 按回合组原子裁剪(ADR-029) |
| 3 | 工具串行 await | asyncio.gather 并行(ADR-021) |
| 4 | SSE JWT 走 URL query | 一次性 ticket 60s(ADR-051) |
| 5 | Backend 持有 Harness 实例 | 只在子进程跑(ADR-020) |
| 6 | sequence_no 用 max+1 | per-session 序列或 advisory_xact_lock(ADR-060) |
| 7 | secret 共用 | 三密钥独立 + 启动校验(ADR-050) |
| 8 | ask 权限用轮询 | Redis BLPOP 阻塞(ADR-028) |
| 9 | Fork 覆盖 model | 3 条 prompt-level 硬约束(ADR-034) |
| 10 | PluginBuilder 硬编码 5 轮 | 完整度打分动态(ADR-038) |

---

## Task 执行标准流程(每个 Task 必走)

参考 `PRD_V4/DOC-CC-ONBOARDING.md` §4 的 9 步流程:

1. 读 Task Part A + Part B + 上游交叉引用
2. 创建分支 / 读状态文件(PROGRESS.md / DECISIONS.md / HANDOFF-LOG.md)
3. **Part B 就是实施 plan**(文件列表 / 函数签名 / 验证步骤已齐全),无需再写 `.plan/<task-id>.md`;
   仅当 Part B 内部有歧义或需要决策子步顺序时,在 HANDOFF-LOG 顶部写 50-100 字"本 Task 执行策略"备忘
4. 加载 superpowers:test-driven-development → 先写失败测试(用 Part B 的验证步骤作测试初稿)
5. 实现 → 跑 Part B 验证步骤(所有断言必须 PASS)
6. 失败升级:1 次自 debug → 2 次 advisor 介入 → 3 次中断人工
7. 加载 superpowers:verification-before-completion → 对照十项质量门
8. 加载 superpowers:requesting-code-review → code-reviewer 独立审查
9. commit + 更新 PROGRESS.md / DECISIONS.md / HANDOFF-LOG.md

---

## 会话/PR 粒度

- **1 Task = 1 Sonnet session**(避免上下文污染)
- **1 DOC = 1 PR**(约 14 个 PR,Task 间在同一 branch 渐进 commit)
- **DOC 完成后**开 PR,/autofix-pr 远程监控

---

## Advisor 介入红线(Opus 只在这三条触发时打断)

1. 违反六原则
2. 超出本 Task 范围的删除/重构
3. 验证失败 ≥ 2 次

其他情况 Opus 沉默或只发建议 tag。

---

## Skill 优先级(冲突时)

**用户/PRD 合同 > superpowers > 系统默认**。PRD 的 ADR 等同 CLAUDE.md 级别,优先于 superpowers rigid 要求。

举例:某 skill 要求"必须 TDD",但 PRD Task 是"补一个只读 GET 端点",强行 TDD 成本大于收益,PRD 的"最小实现"精神优先。

---

## 关键文件索引

| 文件 | 用途 | 更新频率 |
|---|---|---|
| `CLAUDE.md` | 本文件,心智模型硬底线 | 稀少 |
| `PROGRESS.md` | Task 状态表 | 每 Task 完成 |
| `DECISIONS.md` | ADR 落地台账 | 每 ADR 落地 |
| `HANDOFF-LOG.md` | 跨 session 交接 | 每 session 结束 |
| `PRD_V4/DOC-XX-v4.md` | PRD 真相源 | 冻结(改需授权) |
| `PRD_V4/DOC-CC-ONBOARDING.md` | 完整先导文档 | 冻结 |
| `PRD_V4/2026-04-18-execution-strategy-design.md` | 执行策略 spec | 冻结 |
| `.plan/<task-id>.md` | 单 Task 实施计划 | 每 Task 开工 |

---

## 不可做清单

- ❌ 修改 PRD v4 文档本身(除非用户明确授权)
- ❌ 删除或跳过 Part B 的验证步骤
- ❌ 用 `--no-verify` 跳 hook
- ❌ 把 secret 写到 .env 之外
- ❌ 改 Schema 不跑 alembic revision
- ❌ 跨 DOC refactor(当前 Task 无关的代码不动)
- ❌ 自行决定回退 commit(走 §10.2 Phase 级回退流程)
