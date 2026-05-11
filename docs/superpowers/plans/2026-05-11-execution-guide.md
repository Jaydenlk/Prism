# Prism 架构重构 — 执行指南

> 新 session 开工必读。读完这个文件就知道做什么、怎么做、按什么顺序。

---

## 读什么

| 文件 | 内容 | 何时读 |
|---|---|---|
| `HANDOFF-LOG.md` 最新两条 | 用户风格 + 运行时 bug + 产品方向 | 每个 session 开头 |
| `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` | Master spec — 完整架构设计 | 首次开工 |
| `docs/superpowers/plans/2026-05-11-phase-{A..F}-*.md` | 各阶段执行计划 | 做到哪个 phase 读哪个 |

---

## 执行顺序

```
Phase A → Phase B → Phase C → Phase D → Phase E → Phase F
  SDK       多模型     记忆      验证      路由      集成
```

**严格顺序，不能跳。** 每个 phase 依赖前一个的产出。

---

## 每个 Phase 的工作流

1. 读对应 phase 的 plan 文件
2. 加载 `superpowers:using-git-worktrees`（worktree 隔离开发）
3. 逐 Task 执行（用 `superpowers:subagent-driven-development` 派 subagent）
4. 每个 Task 完成后验证
5. Phase 完成后：
   - `simplify` 审查
   - `project-review:pjr` lint/build
   - `git-merge-to-develop` 合并
   - Playwright E2E 测试
6. 更新 PROGRESS.md + HANDOFF-LOG.md

---

## 用户工作风格（必读）

1. **不要问方向，直接做** — "你看着做决策""不用问我""我只负责验收"
2. **功能必须真实可用** — 安装是假的、调用不通的不算完成
3. **并发 subagent** — 独立任务并行执行
4. **发现 bug 就修** — 不拖延
5. **不要复述** — 简短汇报结果
6. **反打补丁** — 深度融合代码，不加 if 绕过

---

## 技术约束

- **可直接用代码**：Claude Code 源码、Claude Agent SDK
- **可借鉴架构**：Poco（不抄代码）
- **前端已完成**：`frontend-react/` — React 18 + TS + Vite，不需要重做
- **后端保留**：FastAPI，清理 API 契约即可
- **新 executor**：`executor_v2/` → Phase A-E 逐步构建 → Phase F 替换旧 executor

---

## 当前状态快照

| 组件 | 状态 |
|---|---|
| 前端 (frontend-react/) | ✅ Phase 1-6 完成，已合并 develop |
| 后端 (backend/) | ⚠️ 20 项审计修复已做，API 基本可用 |
| 旧 Executor (executor/) | ❌ 15K LOC 自研，thinking block bug，待替换 |
| 新 Executor (executor_v2/) | 🔲 未开始 — Phase A |
| UserBrain | 🔲 未开始 — Phase C-E |
| Docker | ⚠️ 可用，nginx 静态路径需更新 |
| Skills Market | ⚠️ 搜索可用，skill_invoke 已实现但未验证 |

---

## Poco 源码参考位置

本地路径：`E:\Agent program\PrismV3\poco-claw-main`

可参考的架构思路（不抄代码）：
- `poco-claw-main/executor/` — Hook 设计模式
- `poco-claw-main/executor_manager/` — 调度架构
- `poco-claw-main/backend/services/callback_service.py` — callback 协议
- `poco-claw-main/specs/` — 设计文档

---

## 关键决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| Executor 重写 vs 修补 | 重写 | 自研 15K LOC 胶水太多，SDK 更可靠 |
| 先 executor 还是先 UserBrain | 先 executor | 引擎不转，上层白做 |
| mem0 vs 自研记忆 | mem0 | 成熟方案，向量+图谱，不造轮子 |
| Context7 用途 | 事实验证 + 文档增强 | 弱模型补偿的关键组件 |
| 前端框架 | 保留 React + TS | 本 session 刚完成迁移，不重做 |
| 产品定位 | 个人助手（非开发者工具） | 区别于 Poco |
