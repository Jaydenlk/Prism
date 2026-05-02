# Handoff: main → implementer (Task 5 / W5 / L5b)

## 状态: READY_FOR_REVIEW

> **Pre-condition**: Batch 1 (Tasks 1, 3, 4 + 2) ✅ 全部 commit (HEAD 6c10cd4 + bf1b21c)。Batch 2 释放。

## 任务描述
为 MCPClient 加 HTTP Streamable transport 分支（MCP spec 2025-03-26），并在 PluginHost 加 transport dispatch 逻辑。stdio 分支保持不变。

## 输入文件范围（仅这些）
- 修改: `executor/plugins/mcp_client.py` (重构现有 stdio 实现 → 加 HTTP 分支；现有 stdio 方法重命名为 `_stdio` 后缀的内部方法，公开方法 dispatch on transport)
- 修改: `executor/plugins/host.py` (`_start_mcp_server` dispatch on transport 字段)
- 创建: `executor/tests/test_mcp_client_http.py`
- 创建: `executor/tests/test_plugin_host_dispatch.py`
- 只读参考:
  - 探测过的 exa server 行为（DEC-005: protocolVersion 2025-03-26, SSE 响应, Mcp-Session-Id stateful）
  - MCP spec primary source: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

## 禁止触碰
- `executor/__main__.py` (Task 6 在改)
- `executor/plugins/skill_loader.py`
- 任何 backend 文件
- 任何 frontend 文件

## 产出预期
- 实现 plan `Task 5` 全部 6 步
- HTTP 分支 + stdio 分支测试都 PASS（不能 break stdio）
- 完成后更新本 handoff: `READY_FOR_IMPL` → `READY_FOR_REVIEW`

## 决策上下文
- DEC-005: exa MCP 实测 protocolVersion=2025-03-26，SSE 响应 (`Content-Type: text/event-stream`)，stateful `Mcp-Session-Id`
- DEC-004: HTTP 分支必须支持 410 Gone → 清 session_id + reinitialize + retry once
- DEC-004: HTTP request 必须带 `Content-Type: application/json` + `Accept: application/json, text/event-stream` + (后续) `Mcp-Session-Id` 头
- 用 `httpx.AsyncClient` (项目已依赖)，不引第三方 mcp SDK
- SSE 解析格式：`event: message\ndata: <json>\n\n`，可能多帧；只取 `id` 匹配的那帧 result
- stdio 现有逻辑零变更（重命名内部方法不算变更行为）
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- MCPClient 重构: 添加 transport 参数，stdio 内部方法重命名为 `_stdio` 后缀，新增 HTTP 分支
- HTTP 分支: POST + Accept text/event-stream + Mcp-Session-Id 持久化 + 410 reinit + retry once
- SSE 解析: `_parse_sse_for_result` 按 id 匹配帧
- `list_tools()` 公开方法 dispatch on transport（stdio 返回缓存，HTTP 发 live request）
- host.py `_start_mcp_server` 签名改为 `(self, server_config: dict)`, 内部 dispatch on transport
- host.py 内部 caller 更新为 `{**mcp_conf, "name": qualified_server}` 形式
- host.py `MCPClient` 从 `TYPE_CHECKING` 移到顶层 import（patch 可用）
- host.py `_start_mcp_server` 使用 `await client.list_tools()` 注册工具
- 5 新测试 + 119 现有测试全部 PASS（零回归）

## 产出物
- `executor/plugins/mcp_client.py`: 重构后含 stdio+HTTP 双 transport 支持
- `executor/plugins/host.py`: `_start_mcp_server` transport dispatch + 顶层 MCPClient import
- `executor/tests/test_mcp_client_http.py`: 3 HTTP transport 测试
- `executor/tests/test_plugin_host_dispatch.py`: 2 host dispatch 测试
- `executor/tests/__init__.py` + `executor/tests/conftest.py`: 测试基础设施
- commit: 76d91ef

## 遗留问题
- `executor/__main__.py` 中 MCPClient 的集成（Task 6 W6 的范围）
- `backend/tests/test_plugin_validate_dispatch.py` 的 8 个 ERROR 是网络连接错误（尝试连接本地 backend 服务器），与本次改动无关，属于预存在问题
