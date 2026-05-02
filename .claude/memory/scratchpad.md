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
