# Prism 架构重构 — 交接 Prompt

> 复制以下内容作为新 session 的第一条消息。

---

你好，我是 Prism 的创始人。请先读以下文件获取完整上下文，然后从 Phase A 开始执行：

1. `HANDOFF-LOG.md` — 读最新两条（2026-05-09 session），包含产品方向、用户工作风格、运行时 bug、架构决策
2. `docs/superpowers/plans/2026-05-11-execution-guide.md` — 执行指南，包含所有计划索引、技术约束、当前状态
3. `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` — Master Spec，完整架构设计
4. `docs/superpowers/plans/2026-05-11-phase-A-sdk-integration.md` — Phase A 详细计划

关键背景：
- Prism 基于 Claude Agent SDK 理念但实际 executor 是 100% 自研的 15K LOC 胶水代码，需要用 Claude Agent SDK 重写
- 致命 bug：AnthropicDriver 丢弃 thinking blocks → 所有多轮工具调用崩溃
- 产品定位：个人助手 agent system（不是开发者工具），弱模型要达到 Claude 80-90% 效果
- 已完成：React 前端迁移（116 文件）、20 项后端审计修复、Skills Market 重构
- 待做：7 个 Phase（A→B→C→D→E→E2→F），49 个 Task

执行要求：
- 严格遵循 superpowers 流程（worktree / simplify / PJR / merge / E2E）
- 允许并开 subagent，独立任务并行执行
- 不要问我方向，直接做决策，我只负责验收
- 功能必须真实可用，不接受假功能
- 发现 bug 当场修，不拖延
- 反打补丁：深度融合代码逻辑，不加 if 绕过

开始 Phase A。
