# Active Plan

> 当前正在执行的任务计划。主 agent 维护,子 agent 只读自己相关的部分。
> 任务完成后归档到 `.claude/plans/archive/`。

## 任务: workflow upgrade dry-run — 验证子 agent 派单 + handoff 状态机 + 决策记录链路

## 状态: DONE(归档于 2026-05-02)

## 涉及文件/模块
- `frontend/Prism.html`(只读)
- `frontend/admin.html`(只读)
- `backend/app/`(只读 1-2 个入口文件)
- `.claude/plans/handoff-main-to-explorer-frontend-structure.md`(handoff 卡)
- `.claude/memory/decisions.md`(决策追加)

## 步骤
1. [x] 写 DEC-001 到 decisions.md → 执行者: main
2. [x] 起 active-plan.md → 执行者: main
3. [x] 创建 handoff-main-to-explorer-frontend-structure.md(5 字段) → 执行者: main
4. [x] 派 general-purpose 模拟 explorer 执行结构摸底 → 执行者: subagent (模拟 explorer)
5. [x] 验证子 agent 是否守了范围 + 回填 handoff → 执行者: main(全 PASS,见 decisions.md DEC-002)
6. [x] 归档 handoff 到 archive/,更新本计划状态为 DONE → 执行者: main

## 相关决策
- DEC-001: 选 explorer 排除 implementer 因纯只读;排除 Explore 因要测项目级 subagent 链路

## 当前阻塞
- 无(注:刚部署的 .claude/agents/*.md 在本会话不可被 Agent 工具直接调用,需 session 重启;dry-run 用 general-purpose 模拟,验证行为机制而非加载机制)
