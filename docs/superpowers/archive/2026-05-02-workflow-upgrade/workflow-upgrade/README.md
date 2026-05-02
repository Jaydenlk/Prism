# Workflow Upgrade — 目录结构说明

## 使用方式
将 `CLAUDE.md` 放到项目根目录，`.claude/` 整个目录放到项目根目录下。
项目级测试没问题后，CLAUDE.md 的内容迁移到全局 `~/.claude/CLAUDE.md`，agents 和 rules 迁移到 `~/.claude/` 对应目录。

## 文件清单

```
项目根/
├── CLAUDE.md                              ← 路由器，只放硬约束和指针
└── .claude/
    ├── agents/                            ← 子 agent 定义
    │   ├── implementer.md                 ← 代码实现（Sonnet，有写权限）
    │   ├── reviewer.md                    ← 代码审查（Opus，只读）
    │   ├── qa-engineer.md                 ← 端到端测试（Haiku，只读）
    │   └── explorer.md                    ← 代码探索（Haiku，只读）
    ├── rules/                             ← 规则文件，按需加载
    │   ├── dev-principles.md              ← 5 条开发原则
    │   ├── subagent-constraints.md        ← 子 agent 派单 & 通信协议
    │   ├── anti-drift.md                  ← 防漂移 & 防摸鱼规则
    │   ├── acceptance-frontend.md         ← 前端验收标准（path-scoped）
    │   └── acceptance-backend.md          ← 后端验收标准（path-scoped）
    ├── memory/                            ← 持久化记忆
    │   ├── decisions.md                   ← 决策日志（选了什么排了什么）
    │   └── scratchpad.md                  ← 临时发现（发现但不当场处理的问题）
    ├── plans/                             ← 任务计划 & handoff
    │   ├── active-plan.md                 ← 当前任务计划
    │   └── archive/                       ← 已完成任务的归档
    └── hooks/                             ← 预留，后续可加 PreToolUse 等 hook
```

## 与现有 superpowers 体系的关系

这套文件**不替代** superpowers 的 skill 调用链。
superpowers 管的是"做事的流程"（brainstorming → plan → worktree → simplify → PJR → merge）。
这套文件管的是"做事的纪律"（不漂移、不摸鱼、通信有协议、决策有记录）。

两者互补，不冲突。superpowers 的 skill 照常触发，触发时遵守这里定义的行为规则。

## 测试建议

1. 先跑一个中等复杂度的任务（涉及前后端、需要 2-3 个子 agent）
2. 观察子 agent 是否遵守文件范围限制
3. 观察 decisions.md 是否被正确追加
4. 观察 handoff 文件是否在子 agent 之间正确流转
5. 观察是否出现"顺便"改了别的东西的情况
6. 跑完后检查 token 消耗是否有明显下降
