# Decision Log

> 记录每次 brainstorming / plan 阶段的决策。选了什么、排了什么、为什么排。
> 只有主 agent 有权写入此文件。子 agent 需要的决策上下文由主 agent 提炼后注入 handoff。

## 格式规范

```
## DEC-{序号} | {日期} | {主题}
选择: {选定方案}
排除: {被排除的方案}（原因：{为什么排}）
影响范围: {哪些模块/文件受影响}
备注: {如有补充}
```

## 使用规则

1. brainstorming 阶段结束后，主 agent **必须**检查是否产生了新决策，有则追加
2. writing-plans 阶段结束后，主 agent **必须**检查计划中的技术选型是否已记录
3. 子 agent 遇到需要决策的情况→上报主 agent，由主 agent 记录
4. 每条记录尽量简短，重点是**排除项和排除原因**
5. 长上下文失忆时，此文件是恢复上下文的第一锚点

---

<!-- 以下为实际记录，新条目追加到底部 -->

## DEC-001 | 2026-05-02 | workflow upgrade dry-run 子 agent 选型
选择: explorer(只读、范围锁定、Haiku 模型,适合纯结构摸底)
排除: implementer(原因:本任务零代码改动,不需要写权限);Explore 全局 agent(原因:dry-run 目标是验证项目级 explorer 子 agent + handoff 工作流,而非通用探索)
影响范围: .claude/plans/handoff-main-to-explorer-frontend-structure.md(本次 dry-run 唯一 handoff)
备注: dry-run 验证内容 — (a) 5 字段派单是否被守、(b) handoff 状态机回填、(c) 子 agent 是否未碰 decisions.md / 范围外文件、(d) 主 agent 是否独占决策记录写入

## DEC-002 | 2026-05-02 | dry-run 合规性结论
选择: workflow upgrade 上线(项目级 subagent + handoff 状态机机制运转正常)
排除: 暂不撤回部署(原因:行为合规全 PASS,技术加载机制只需 session 重启即可激活)
影响范围: 整个 .claude/ 部署,所有未来子 agent 派单遵循本次验证的派单纪律
备注: dry-run 实测 PASS 项 — (a) 5 字段派单格式被严格读取并执行;(b) handoff 顶部状态从 READY_FOR_IMPL → READY_FOR_REVIEW 自动回填;(c) 子 agent 仅读 handoff 范围内 3/4 文件(styles.css 自判不必要跳过 — 边界判断良好);(d) decisions.md / 其他 handoff / 后端 / PRD_V4 全部未触碰;(e) 子 agent 输出 39 行 ≤ 50 限制;(f) 子 agent token 57k / 20 tool_uses,作为 baseline 记录。待 session 重启后用 Agent(subagent_type='explorer') 直接调用做加载机制验证
