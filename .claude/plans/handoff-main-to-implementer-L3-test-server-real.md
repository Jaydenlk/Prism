# Handoff: main → implementer (Task 2 / W2 / L3 + cleanup)

## 状态: READY_FOR_REVIEW

## 任务描述
两件事打包：
1. **L3 主体**：删除 `POST /mcp-servers/{id}/test` 的 stub，改成真实拉起 MCPClient 探测连接（plan Task 2 的 5 个 step）
2. **Schema 统一清理**（Batch 1a 残留）：W4 引入了新 `McpServerCreate/Response/Update/Base` 但保留旧 `CreateMCPServerRequest/MCPServerResponse` 共存 — CLAUDE.md A.2「最简代码原则」要求清零冗余。本任务必须把 mcp_service `_to_server_response` 和 mcp.py 路由的 response_model 全部迁到新 schema，**删除旧 schema** + 同步任何 caller (provider tests / 其他 caller)；新 `McpServerResponse` 加 `created_at` 字段（旧 schema 有，新里要补全），并新增 `transport / url / headers` 字段（headers 走 mask，url 是 http 才有）

## 输入文件范围（仅这些）
- 修改: `backend/app/services/mcp_service.py` (`test_server` 方法 + `_to_server_response` 方法 — 后者要返新 schema 字段)
- 修改: `backend/app/api/v1/mcp.py` (test endpoint 路由；其他 endpoint 的 `response_model=` 全部从 `MCPServerResponse` 改为 `McpServerResponse`)
- 修改: `backend/app/schemas/mcp.py` (**删除** `CreateMCPServerRequest` + 旧 `MCPServerResponse`；给新 `McpServerResponse` 加 `created_at: datetime` 字段；mask 头部时保持 W4 已有的逻辑)
- 创建: `backend/tests/test_mcp_test_server.py`
- 只读参考:
  - `executor/plugins/mcp_client.py` (现有 stdio 实现)
  - `backend/app/models/mcp_server.py`
  - 任何 import 旧 schema 名称的 caller（grep `CreateMCPServerRequest\|MCPServerResponse` 找全）

## 禁止触碰
- `_BUILTIN_MCP_SERVERS` 常量（W3/W6 在改）
- `register_builtin_servers` 方法（W3 已重构完，本 task 不动它）
- 任何 frontend 文件
- 任何 executor 文件
- alembic migration

## 产出预期
- 实现 plan `Task 2` 全部 5 step（test_server 真连）
- 完成 schema 统一清理（删旧 schema + 迁所有 caller + 新 schema 加 created_at + 新 schema 含 transport/url/(masked)headers）
- `grep 'CreateMCPServerRequest\|MCPServerResponse' backend/` 应返回 0 结果（除被删除点）
- 现有 mcp 相关测试全 PASS（不能 break Batch 1a 的 16 tests + provider/credential 等其他模块）
- test_mcp_test_server.py 新增 4 测试 PASS（http transport 因 W5 还没合并 — 不要 skip 而是测 graceful 兜底返 success=False）
- 完成后更新本 handoff 状态: `READY_FOR_IMPL` → `READY_FOR_REVIEW`

## 决策上下文
- DEC-004: stdio 真连必须用 MCPClient (现有，executor 侧)，backend 可以 import executor 模块（不违反进程边界—因为是 transient 一次性测试连接）
- DEC-004: 10s timeout 是硬上限（用户 UI 不能挂太久）
- HTTP transport 测试在 Task 5 (W5) 落地后才能真跑，本任务只写 graceful 兜底（"http transport branch not yet available"）
- 返回结构 `{success, tools, error, latency_ms}`，frontend MCP servers tab "测试连接"按钮消费
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- 删除旧 `CreateMCPServerRequest` 和 `MCPServerResponse` schema
- 新 `McpServerResponse` 加 `created_at: datetime` + `model_config from_attributes`
- `mcp_service._to_server_response` 改返新 `McpServerResponse`（含 transport/url/masked headers）
- `mcp_service.test_server` 替换 stub → async 真连接（MCPClient + 10s timeout）
- `mcp.py` 所有 endpoint `response_model=` 改为 `McpServerResponse`；test endpoint 改 async dict 返回
- `test_mcp_http_schema.py::test_response_masks_authorization` 补 `created_at` 参数（schema 字段新增导致）
- 创建 `backend/tests/test_mcp_test_server.py`（4 tests PASS）
- 全套回归：114 passed（+4 新增），0 新增失败

## 产出物
- `backend/app/schemas/mcp.py`: 删旧 schema，McpServerResponse 加 created_at
- `backend/app/services/mcp_service.py`: 异步 test_server + 新 _to_server_response
- `backend/app/api/v1/mcp.py`: 所有 response_model 迁新 schema，test endpoint async
- `backend/tests/test_mcp_test_server.py`: 4 新测试
- Commit 1: 1001e24 (schema cleanup)
- Commit 2: bf1b21c (L3 real connection)

## 遗留问题
- `MCPTestResponse` schema 仍在 mcp.py 中（未被 mcp.py 直接 import 但 mcp_service 也不再使用）— 如需彻底清除 MCPTestResponse 需主 agent 决策（它是 schemas/mcp.py 的公开类型，其他代码可能引用）
