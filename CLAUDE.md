# Prism v2 — Claude Code 项目指引

> **适用**: 本仓库所有 Sonnet / Opus 会话
> **版本**: 1.1(2026-04-20 用户硬规则锁定)
> **完整版**: `PRD_V4/DOC-CC-ONBOARDING.md`
> **执行策略**: `PRD_V4/2026-04-18-execution-strategy-design.md`

---

## 🔴 用户硬规则(2026-04-20 锁定 — 优先级最高,凌驾下方所有)

### A. 五条开发原则(硬底线,贯穿全部代码改动)

1. **单一职责原则** — 每个服务、方法只负责一个明确的职责域,避免职责混乱
2. **最简代码原则** — 不做向后兼容,宁愿破坏性更新也要保证代码最简化,删除所有冗余代码
3. **类型严格原则** — 所有 TypeScript / Python 类型必须正确,不使用 `any`,编译错误立即修复
4. **KISS 原则** — 保持简单直接,如果需要解释就是太复杂了
5. **文档置信度原则** — 绝不基于推测写代码,必须基于真实可验证的技术文档。涉及支付 / 数据库 / API / 认证签名 / 加密 等关键功能时,文档置信度不足必须停下,要求用户提供准确资料

### B. Skill 加载硬要求(任一缺失 → 立即停止任务告知用户,严禁盲目无 skill 执行)

任何任务开工 → `superpowers:using-superpowers` 已自动加载

| 阶段 | 必加载 skill |
|---|---|
| 创意 / 新功能 / 修改行为 | `superpowers:brainstorming` 必先 |
| 多步任务 / 写实施 plan | `superpowers:writing-plans` |
| 实施代码 | `superpowers:test-driven-development` + `superpowers:using-git-worktrees`(隔离开发) |
| 调试任何 bug / 测试失败 / 异常行为 | `superpowers:systematic-debugging`(根因优先,Phase 1 没完不许提 fix) |
| 完工审查阶段 | `simplify`(3 subagent 并行 reuse / quality / efficiency)→ `project-review:pjr`(lint / build / 逻辑 / 合并)→ `superpowers:requesting-code-review` |
| 合并到 develop | `git-merge-to-develop:git-merge-to-develop` 必先加载 |
| 涉及前端(任何 UI 改动) | **追加** `frontend-design` **和** `ui-ux-pro-max:ui-ux-pro-max` 两个 skill |

**严格遵循 superpowers 系列原则。skill 找不到 → 立即停 + 告知用户,不准盲目执行。**

### C. Worktree 隔离硬要求

- **所有开发必须在 git worktree 里执行**(`.worktrees/<topic>/`)
- 例外:任务**非常简单**(单文件改 1-3 行 / 文档改 / 配置 toggle),可不用 worktree
- 涉及前后端逻辑改动 / 多文件 / 跨模块 → 必须 worktree

### D. 端到端测试硬要求(用户最严)

- 用 **Playwright 直接测试**(MCP 浏览器或 local Playwright runtime)
- **不是只写测试脚本**,要真实驱动浏览器走流程
- **桌面端 + 移动端双端必测**(viewport 桌面 ≥1280 / 移动 390×844)
- **每个按钮 / 每个流程完全模拟人走一遍**:注册 / 登录 / CRUD / 取消 / 确认 / 失败路径都要触发并断言
- **看到页面渲染没问题 ≠ 通过**;必须验证状态变更(network 请求 / DB 写入 / UI 更新)和 error path

### E. 反打补丁硬规则(严格禁止)

- 任何修改 / 修复 / 新增,**严禁**绕过根因打补丁
- 必须**深度融合到代码逻辑内部**,通过**重构 / 调整 / 结合现有逻辑** 实现改变
- 出现"加一层 if"、"兜底默认值"、"特殊路径绕过"的冲动 → 先问"根因是什么,能否在源头解决"
- 最终代码**必须最简**(过程可复杂,结果简洁,完整实现需求)
- systematic-debugging Phase 1(reproduce / read errors / trace data flow)未完成,**不许提 fix**

### F. 文档置信度扩展硬规则

- 任何官方 / 外部接口:开工前 **WebFetch primary source**(不只看二手调研)
- 任何参考资料:用 **exa MCP**(`mcp__exa__web_search_exa` / `mcp__exa__web_fetch_exa`)穷尽搜集 — 官方手册 + 真实案例 + 工作原理
- 调研报告 vs 官方冲突 → 以官方为准 + 写 `docs/superpowers/blockers/<date>-<topic>-blocker.md` 通知用户
- 关键功能(支付 / DB / API / 认证 / 签名 / 加密)文档置信度不足 → 停 + blocker + 等用户资料,不许靠推断写代码

### G. 需求理解硬规则

- 从**业务角度**理解需求,保证**链路完整** + **符合用户思维**
- 充分**探索现有代码**(grep / Read / 读 PRD)再开发
- 技术方案上,只需遵循需求 + 明确含义 + 链路完整;不假设技术栈,确认后写

### H. PJR 阶段对前端硬要求

- PJR 不只是后端检查;前端 **lint + build 必须完整执行**(`node --check` / npx eslint / 必要时 build)
- 任何只跑后端 PJR 的会话视为不合格

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
