# Active Plan — Plugin Bootstrap (2026-05-02)

> 当前任务的子 agent 派单计划。每任务覆盖。完成后归档到 `.claude/plans/archive/`。

## 总目标
修复"executor `__main__.py` Step 3d 从未实例化 PluginHost / SkillLoader"根因 + 加 HTTP transport + 集成 exa/Brave/Tavily 三家搜索 builtin。

## Spec & Plan
- Spec: `docs/superpowers/specs/2026-05-02-plugin-bootstrap-design.md`
- Plan: `docs/superpowers/plans/2026-05-02-plugin-bootstrap.md`

## Branch
`feat/plugin-bootstrap` (worktree: `.worktrees/plugin-bootstrap`)

## 派单状态

### Batch 1a (parallel sonnet x3) — IN FLIGHT
| Task | Worker | Handoff | TaskList ID | 状态 |
|---|---|---|---|---|
| Task 1 / L1 | implementer (W1) | `handoff-main-to-implementer-L1-internal-endpoints.md` | #1 | READY_FOR_IMPL → 运行中 |
| Task 3 / L4+L7 | implementer (W3) | `handoff-main-to-implementer-L4L7-marketplace-stdio-builtins.md` | #4 + #8 | READY_FOR_IMPL → 运行中 |
| Task 4 / L5a | implementer (W4) | `handoff-main-to-implementer-L5a-http-transport-schema.md` | #5 | READY_FOR_IMPL → 运行中 |

### Batch 1b (sequential after 1a) — QUEUED
| Task | Worker | Handoff | TaskList ID | 状态 |
|---|---|---|---|---|
| Task 2 / L3 | implementer (W2) | `handoff-main-to-implementer-L3-test-server-real.md` | #3 | 等待 1a |

> 排队原因: T2 与 T3 都改 `mcp_service.py`，串行避免文件写竞态。

### Batch 2 (parallel sonnet x2) — QUEUED
| Task | Worker | Handoff | TaskList ID | 状态 |
|---|---|---|---|---|
| Task 5 / L5b | implementer (W5) | `handoff-main-to-implementer-L5b-mcp-http-branch.md` | #6 | 等待 Batch 1 |
| Task 6 / L2+L6 | implementer (W6) | `handoff-main-to-implementer-L2L6-executor-bootstrap-exa.md` | #2 + #7 | 等待 Batch 1 |

### Batch 3 — QUEUED
| Task | Worker | TaskList ID | 状态 |
|---|---|---|---|
| Task 7 / L8 | qa-engineer (W7) | #9 | 等待 Batch 2 |

## 下一步触发
Batch 1a 完成后:
1. 主 agent 集成: 检查 git log, run pytest 确认 4 任务测试都 PASS (T1 的 http skip 在 T4 完成后应当转 PASS — 触发再跑一次)
2. 派 T2 (W2) 单独跑
3. T2 完成 → 派 Batch 2 (W5 + W6 并行)
4. Batch 2 完成 → 派 W7 qa-engineer 跑 e2e Playwright 真实 exa 调用

## 状态机流转
`READY_FOR_IMPL → READY_FOR_REVIEW → DONE` (单 implementer 任务)

子 agent 完成时回填 handoff 顶部状态 + "已完成" + "产出物" + "遗留问题" 段落。主 agent 读后归档到 `.claude/plans/archive/`。

## 归档前一任务
旧的 `workflow upgrade dry-run` 任务（DEC-001/002/003）完成于 2026-05-02 早些时候，归档应在 `.claude/plans/archive/` 下，本文件已被新任务覆盖。
