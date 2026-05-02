# Scratchpad

> 临时共享状态。主 agent 和子 agent 都可以写入。
> 用于记录"发现了但当前不处理"的问题，避免打断当前任务流。
> 每个任务完成后由主 agent 清理：已处理的删除，需要跟进的转移到 plans 或 decisions。

## 格式

```
- [{日期}] [{发现者: main/implementer/reviewer/qa}] {内容}
```

---

<!-- 以下为实际记录 -->

## 2026-05-02 W4 完成后遗留待 W2 期间清理
- backend/app/schemas/mcp.py 现存两套 schema 共存:
  - 旧: CreateMCPServerRequest, MCPServerResponse (含 created_at)
  - 新 (W4 加): McpServerBase, McpServerCreate, McpServerUpdate, McpServerResponse
- backend/app/services/mcp_service.py `_to_server_response` 不返 transport/url/headers — 导致 admin.html McpServers 列表的 transport 列为空
- api/v1/mcp.py 路由的 response_model 仍用旧 MCPServerResponse
- 处理时机: W2 的 handoff 加 directive，让它顺手统一（W2 反正要改 mcp.py + mcp_service.py）

## 2026-05-02 plugin-bootstrap 完工后已知不动账（separate PR）
- 前端 tool_card output 渲染：消息持久化的 tool_use 块在 tool_start + message_complete 两次回写，造成 DB 出现 input:{} 的重复 tool_use 行；前端按 tool_use_id 配对 tool_result 时，被空 input 的副本覆盖，导致 .tool-body output pre 为空
  - 修复方向：callback_service._handle_tool_start 不写 placeholder Message，只在 message_complete 写完整 assistant 块；或前端做去重 by tool_use_id 取 input 非空那条
  - 影响：UI tool_card 看不到 exa 返回的 URL（仅在 final 消息的 markdown 渲染中可见）
  - 不阻塞 plugin-bootstrap 交付（功能链路完整，agent 真在用 exa）
- backend/app/schemas/mcp.py 还有 MCPTestResponse 类未被任何 caller 引用 — 留待 simplify 阶段一起删
