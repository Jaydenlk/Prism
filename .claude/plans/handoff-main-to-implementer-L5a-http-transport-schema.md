# Handoff: main → implementer (Task 4 / W4 / L5a)

## 状态: READY_FOR_REVIEW

## 任务描述
为 mcp_servers 加 HTTP transport schema：DB migration + ORM model + Pydantic schema + 前端 admin tab UI 联动。

## 输入文件范围（仅这些）
- 修改: `backend/app/models/mcp_server.py` (在 `McpServer` class 加 3 字段)
- 修改: `backend/app/schemas/mcp.py` (字段 + validators + 敏感 header mask)
- 创建: `backend/alembic/versions/010_mcp_http_transport.py`
- 修改: `frontend/admin.html` (MCP servers tab — transport radio + 条件显示 stdio/http 字段 + headers JSON editor)
- 创建: `backend/tests/test_mcp_http_schema.py`
- 只读参考: `backend/alembic/versions/009_plugin_typed_columns.py` (看现有 migration 风格)

## 禁止触碰
- `_BUILTIN_MCP_SERVERS` (W3/W6 在改)
- `test_server` (W2 在改)
- 任何 executor 文件
- 任何 backend service / api 文件 (除 schema/model)

## 产出预期
- 实现 plan `Task 4` 全部 8 步
- alembic upgrade 成功（在 worktree 内 docker-compose backend 容器跑或本地虚拟环境跑）
- 测试 4/4 PASS
- frontend admin.html MCP tab 加 transport radio + url/headers 条件字段
- 完成后更新本 handoff 状态: `READY_FOR_IMPL` → `READY_FOR_REVIEW`

## 决策上下文
- DEC-004: alembic revision 号 `010_mcp_http`（009 已被 plugin_typed_columns 占）
- DEC-004: `command` 保持 NOT NULL；HTTP 行写占位 `__http__`（避免改约束）
- DEC-004: `transport` 默认 'stdio'（向后兼容现有行）
- DEC-004: `headers_encrypted` 是 TEXT，存 `encrypt_value(json.dumps(headers))` 的 ciphertext
- McpServerResponse 必须 mask Authorization/X-API-Key/X-Auth-Token/Cookie 等敏感 header（保留 scheme prefix 如 "Bearer ***"）
- McpServerCreate validators: transport='stdio' 时 command 不能是 '__http__'；transport='http' 时 url 必填，command 自动补 '__http__'
- frontend 不读 backend 字段直接 render，而是通过 PrismAPI 获取的 response（已 mask）
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- Step 1: 创建 backend/tests/test_mcp_http_schema.py（4 个测试用例）
- Step 3: backend/app/models/mcp_server.py 加 transport/url/headers_encrypted 三字段
- Step 4: 创建 backend/alembic/versions/010_mcp_http_transport.py（revision=010_mcp_http, down_revision=009）
- Step 5: backend/app/schemas/mcp.py 新增 McpServerBase/McpServerCreate/McpServerUpdate/McpServerResponse（保留现有 CreateMCPServerRequest/MCPServerResponse 不动）
- Step 6: frontend/admin.html 新增 McpServers React 组件 + NAV 项 + PAGES 项（transport radio + 条件显示 stdio/http 字段）
- Step 7: 4/4 tests PASS，migration syntax OK
- Step 8: commit adf84a2

## 产出物
- backend/app/models/mcp_server.py: McpServer 加 3 字段
- backend/app/schemas/mcp.py: 新增 4 个 HTTP transport schema 类
- backend/alembic/versions/010_mcp_http_transport.py: migration（revision=010_mcp_http）
- backend/tests/test_mcp_http_schema.py: 4/4 PASS
- frontend/admin.html: McpServers 组件 + NAV 条目 mcpServers

## 遗留问题
- 现有 MCPServerResponse（含 created_at）与新 McpServerResponse（无 created_at）并存，api/service 层仍用旧类；需主 agent 决策何时迁移统一
- admin.html McpServers 组件用 PrismAPI.mcp.listServers() 返回数据，实际 API response 格式需与 mcp_service._to_server_response 对齐（现有 _to_server_response 不包含 transport/url 字段）；主 agent 评估是否需要同步更新 mcp_service
