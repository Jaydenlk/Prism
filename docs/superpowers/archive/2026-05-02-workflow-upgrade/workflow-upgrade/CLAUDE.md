# Project Constitution

> 这是路由器，不是百科全书。只放硬约束和指针，详细规则在 `.claude/rules/` 下按需加载。

## 硬约束（全局生效，不可覆盖）

### 严禁打补丁（最高执行级）
任何修改必须通过重构、调整现有结构、从根源解决。不接受 wrap 一层、加 if/else 兜底、绕过架构。

### 结果代码最简
过程不一定简单，但结果代码必须最简且完整实现需求。修改完成后自审一次，清掉绕路和冗余。

### 禁止 any
TypeScript 类型必须正确，禁止 `any`，编译错误立即修复。

### 文档置信度
不基于推测写代码。涉及支付、数据库、API 等关键功能时，文档置信度不高→停下来向用户索取准确资料。

## 行为边界（防漂移）

1. **不做任务描述之外的事**。发现额外问题→记录到 `.claude/memory/scratchpad.md`，不当场修。
2. **不"顺便"优化**。没被要求的重构、美化、注释补充一律不做。
3. **遇到架构级不确定→停下来问**。不许猜测用户意图，不许假设"大概是这个意思"。
4. **同一文件在一个任务流程内只读一次**。需要回看→引用之前的读取结果。
5. **子 agent 不读全局状态**。主 agent 负责提炼上下文并注入子 agent 的 prompt，详见 `.claude/rules/subagent-constraints.md`。

## 路由表

| 需求类型 | 指向 |
|---|---|
| 开发原则 & coding standards | `.claude/rules/dev-principles.md` |
| 子 agent 派单 & 通信协议 | `.claude/rules/subagent-constraints.md` |
| 防漂移 & 防摸鱼详细规则 | `.claude/rules/anti-drift.md` |
| 决策记录（选了什么排了什么） | `.claude/memory/decisions.md` |
| 当前任务计划 & handoff | `.claude/plans/active-plan.md` |
| 临时共享状态 | `.claude/memory/scratchpad.md` |
| 前端验收标准 | `.claude/rules/acceptance-frontend.md` |
| 后端验收标准 | `.claude/rules/acceptance-backend.md` |

## Compaction 指令

当执行 /compact 时，必须保留：
- 已修改文件的完整列表
- 当前任务的剩余步骤
- 所有未解决的决策点
- `.claude/memory/decisions.md` 中本次会话新增的条目摘要

## Subagent 模型分级

- 架构决策、复杂调试、code review → Opus
- 常规实现、单元测试 → Sonnet
- 文件搜索、Playwright 浏览器操作、格式校验 → Haiku
