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
备注: dry-run 实测 PASS 项 — (a) 5 字段派单格式被严格读取并执行;(b) handoff 顶部状态从 READY_FOR_IMPL → READY_FOR_REVIEW 自动回填;(c) 子 agent 仅读 handoff 范围内 3/4 文件(styles.css 自判不必要跳过 — 边界判断良好);(d) decisions.md / 其他 handoff / 后端 / PRD_V4 全部未触碰;(e) 子 agent 输出 39 行 ≤ 50 限制;(f) 子 agent token 57k / 20 tool_uses,作为 baseline 记录

## DEC-003 | 2026-05-02 | 加载机制验证(更正 DEC-002 误判)
选择: harness mid-session 动态加载 `.claude/agents/` 已确认,**不需要 session 重启**
排除: 原 DEC-002 备注"待 session 重启后验证"的假设(原因:实测当场调用 `Agent(subagent_type='explorer')` 成功,工具集 [Read, Glob, Grep] 与 model=haiku 与 description 全部跟 explorer.md frontmatter 完全一致)
影响范围: 整个 .claude/agents/ 部署 — 现在起所有派单都可直接 `subagent_type=<custom name>`,无需 general-purpose 模拟
备注: 实测 baseline — 单次 explorer 加载验证 13k tokens / 1 tool_use / 3.8s。harness 在 .claude/agents/*.md 文件落地后即时 register,P0 修 qa-engineer.md 的 tools 字段(加 Playwright MCP 通配符)也在系统 agent 列表里被正确反映

## DEC-004 | 2026-05-02 | Plugin bootstrap 架构修复路径
选择: 一次 PR 同时修根因 (PluginHost + SkillLoader 实例化) + 加 HTTP transport + 集成 exa/Brave/Tavily 三家搜索 builtin
排除:
  - 只修根因不加 builtin (原因: 用户已确认 Path C，要 1:1 复用现有 exa key + Tavily/Brave 备选生态)
  - 分两个 PR (原因: HTTP transport 没 builtin 验证就是死代码，e2e 跑不通)
  - 加 SSE-only transport (legacy 2024-11-05 spec) (原因: exa 实测是 Streamable HTTP 2025-03-26，最新 spec)
影响范围: backend (8 文件) + executor (3 文件) + frontend (1 文件) = 12 处改动；3 batch x 7 task 并行 sonnet 实施
备注: secret = headers_encrypted 整体 AES-256-GCM 加密 (复用 app.core.security.encrypt_value)；builtin 用 ${env:VAR_NAME} 占位；env 缺失则跳过注册（graceful）；解密发生在 backend service 层 (executor 不持 ENCRYPTION_KEY，进程边界=信任边界铁律)；alembic 010 (009 已被 plugin_typed_columns 占用)；exa Bearer 用 .env EXA_API_KEY 注入

## DEC-005 | 2026-05-02 | exa MCP 协议探测结果
选择: HTTP Streamable transport (MCP spec 2025-03-26)，SSE 响应，stateful Mcp-Session-Id
排除: 旧 SSE-only transport (2024-11-05 spec) (原因: curl 实测 exa server 用 2025-03-26 协议)
影响范围: MCPClient HTTP 分支必须实现 SSE 响应解析 + Mcp-Session-Id 持久化 + 410 重连
备注: 探测命令 curl -X POST + initialize JSON-RPC 返回 protocolVersion=2025-03-26、Content-Type=text/event-stream、Mcp-Session-Id 头存在；server 是 Vercel 上的 mcp-typescript-server v0.1.0
