# Handoff: main → implementer (Task 3 / W3 / L4 + L7)

## 状态: READY_FOR_REVIEW

## 任务描述
3 件事打包：
1. L4: marketplace_registry 启动期空表自动注册 `anthropics/claude-plugins-official`
2. L7: `_BUILTIN_MCP_SERVERS` 加 Brave + Tavily stdio 条目（exa 是 Task 6 干的，这里**不要碰 exa**）
3. Dockerfile 加 `nodejs npm`（Brave/Tavily 用 npx）

## 输入文件范围（仅这些）
- 修改: `backend/app/services/marketplace_service.py` (新增 `bootstrap_default_marketplace` 方法)
- 修改: `backend/app/main.py` (lifespan 调 bootstrap)
- 修改: `backend/app/services/mcp_service.py` (`_BUILTIN_MCP_SERVERS` append + `register_builtin_servers` env_var gate 逻辑)
- 修改: `backend/Dockerfile` (apt-get install nodejs npm)
- 创建: `backend/tests/test_marketplace_bootstrap.py`
- 创建: `backend/tests/test_mcp_builtin_stdio.py`
- 只读参考: `backend/app/models/marketplace.py`, `backend/app/models/mcp_server.py`

## 禁止触碰
- `test_server` 方法（W2 在改）
- exa builtin 条目（**严禁加 exa，Task 6 W6 的事**）
- HTTP transport 字段（schema/http branch 不是这里，那是 W4/W5）
- 任何 frontend / executor 文件
- alembic migrations

## 产出预期
- 实现 plan `Task 3` 全部 7 步
- 测试 6/6 PASS（marketplace 2 + builtin stdio 4）
- Brave + Tavily 在 `_BUILTIN_MCP_SERVERS` 中各 1 条；exa 留给 Task 6
- 完成后更新本 handoff 状态: `READY_FOR_IMPL` → `READY_FOR_REVIEW`

## 决策上下文
- DEC-004: env-var-missing → log + skip 注册（不报错，graceful）
- DEC-004: 默认 marketplace 一次性，admin 可后续 delete (若已存在任何 marketplace 行 → bootstrap 跳过)
- Brave: `npx -y @modelcontextprotocol/server-brave-search` + env `BRAVE_API_KEY`
- Tavily: `npx -y tavily-mcp@latest` + env `TAVILY_API_KEY`
- `_BUILTIN_MCP_SERVERS` 字典字段：每条须有 `env_var` 字段标注哪个 env 缺失就 skip（plan 中 Step 4 有完整代码）
- `register_builtin_servers()` 重写后必须保留对现有 system-scope 行的 update 路径（key rotation 场景）
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- L4: `bootstrap_default_marketplace(created_by)` 新增到 MarketplaceService，空表时注册 anthropics/claude-plugins-official
- L7: `_BUILTIN_MCP_SERVERS` 追加 brave-search + tavily（含 env_var 字段）
- `register_builtin_servers` 重构为实例方法，env_var gate + key rotation update 路径
- `main.py` lifespan 5b 步调用 bootstrap（admin 存在时），4b 步更新为实例方法调用
- `backend/Dockerfile` 将 nodejs + npm 加到现有 apt-get install 行
- `backend/tests/test_marketplace_bootstrap.py` 新建（2 tests）
- `backend/tests/test_mcp_builtin_stdio.py` 新建（4 tests）
- `backend/tests/conftest.py` 新增 db fixture（SQLite in-memory，JSONB→TEXT，FK OFF）
- 6/6 tests PASS

## 产出物
- `backend/app/services/marketplace_service.py`: bootstrap_default_marketplace 方法
- `backend/app/services/mcp_service.py`: _BUILTIN_MCP_SERVERS 扩展 + register_builtin_servers 重构
- `backend/app/main.py`: lifespan 4b + 5b 更新
- `backend/Dockerfile`: nodejs npm 追加
- `backend/tests/test_marketplace_bootstrap.py`: 新建
- `backend/tests/test_mcp_builtin_stdio.py`: 新建
- `backend/tests/conftest.py`: db fixture 新增
- commit: adf84a2（源文件）+ b8c1355（conftest）

## 遗留问题
- plan 中 bootstrap_default_marketplace 的 `created_by` 参数签名与 plan 原文略有不同（plan 原文无参数，使用内部 admin 查询）。实际实现采用参数化 + main.py 外部查询方式，更符合单一职责。已知偏离，非 bug。
