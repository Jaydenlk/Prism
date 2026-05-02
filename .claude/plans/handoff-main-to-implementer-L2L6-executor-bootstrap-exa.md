# Handoff: main → implementer (Task 6 / W6 / L2 + L6)

## 状态: READY_FOR_REVIEW

> **Pre-condition**: Batch 1 (Tasks 1, 3, 4 + 2) ✅ 全部 commit (HEAD bf1b21c)。Task 5 (W5) 可与本任务并发（两者不共享文件）。

## 任务描述
两件事：
1. **L2 根因修复**: 在 `executor/__main__.py` Step 3d 段落（line 491-509）追加 plugin bootstrap 段 — 通过 backend internal endpoint 拉 user 的 skills + mcp servers，实例化 PluginHost + SkillLoader，注册到 ToolRegistry + assembler。
2. **L6 exa builtin**: 在 `_BUILTIN_MCP_SERVERS` 加 exa HTTP 条目，`register_builtin_servers` 处理 HTTP 类条目（headers_template 替换 env var → 加密 → 存 headers_encrypted）。

## 输入文件范围（仅这些）
- 修改: `executor/__main__.py` (Step 3d 段落，~line 491-509 之后插入)
- 修改: `backend/app/services/mcp_service.py` (在 W3 已建立的 `_BUILTIN_MCP_SERVERS` 末尾追加 exa；扩展 `register_builtin_servers` 处理 HTTP 类条目)
- 创建: `executor/tests/test_plugin_bootstrap_main.py`
- 创建: `backend/tests/test_mcp_builtin_exa.py`
- 只读参考:
  - `executor/plugins/host.py` (Task 5 W5 改完的 dispatch)
  - `executor/plugins/skill_loader.py` (现有 SkillLoader 类)
  - `backend/app/api/v1/internal.py` (Task 1 W1 改完的 endpoints)
  - `backend/app/core/security.py` (encrypt_value)

## 禁止触碰
- `executor/plugins/mcp_client.py` (Task 5 在改)
- `executor/plugins/host.py` (Task 5 在改 — 只读)
- 任何 frontend 文件
- alembic / models / schemas

## 产出预期
- 实现 plan `Task 6` 全部 7 步
- 测试 5/5 PASS（executor bootstrap 2 + exa builtin 3）
- 完成后更新本 handoff: `READY_FOR_IMPL` → `READY_FOR_REVIEW`

## 决策上下文
- DEC-004: 根因 = `executor/__main__.py` Step 3d 从未实例化 PluginHost / SkillLoader — 本任务正面修复
- DEC-004: bootstrap 失败 graceful（log warn + 继续），不能 crash run
- DEC-004: exa Bearer token 来自 `.env` 的 `EXA_API_KEY`；用户已经把他 .claude.json 的 token 复制进来 (key: 24b74e9a-d7e5-4621-b10d-46e7ea44bb65)
- DEC-004: HTTP 类 builtin 的 `headers_template` 用 `${env:VAR_NAME}` 占位，在 register_builtin_servers 中正则替换，加密后存 headers_encrypted
- DEC-005: exa server transport=http, url=https://mcp.exa.ai/mcp
- ENCRYPTION_KEY 不进 executor — assembler.update_tools 接收的是 plaintext headers（已由 internal endpoint 解密）
- `bootstrap_plugins(backend_url, user_id, callback_secret) -> tuple[list, list]` 是新 helper，返回 ([], []) 兜底
- Step 3d 追加位置：在 `pipeline = ToolExecutionPipeline(...)` 之后、`HarnessRuntime(...)` 之前
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- `bootstrap_plugins()` helper 添加到 `executor/__main__.py`（graceful，失败返回 `([], [])`）
- Step 3d-bis 插入 `pipeline = ToolExecutionPipeline(...)` 之后、`HarnessRuntime` 之前：实例化 `HookSystem` + `SkillLoader` + `PluginHost`，遍历 servers_data 加载 stdio MCP servers，调用 `assembler.update_tools()`
- exa entry 追加到 `_BUILTIN_MCP_SERVERS`（transport=http，headers_template with EXA_API_KEY）
- `register_builtin_servers()` 扩展 HTTP 分支：`${env:VAR}` 正则替换 → `encrypt_value` → `headers_encrypted`
- 5/5 新测试 PASS（executor: 2 + backend: 3）
- 全量 backend/tests/: 117 passed, 1 skipped, 8 errors（8 errors 均为 test_plugin_validate_dispatch.py 需要 live backend — 预存在问题，非本任务引入）
- commit: d1e2fe2

## 产出物
- `executor/__main__.py`: 新增 `bootstrap_plugins()` + Step 3d-bis 段落
- `backend/app/services/mcp_service.py`: 追加 exa 条目 + register_builtin_servers() HTTP 分支
- `executor/tests/__init__.py`: 新建（空）
- `executor/tests/test_plugin_bootstrap_main.py`: 2 个测试（bootstrap 正常 + 失败 graceful）
- `backend/tests/test_mcp_builtin_exa.py`: 3 个测试（exa in builtins + skip if no key + encrypted headers）

## 遗留问题
1. **Skill loading from install_path 未完整实现**（需主 agent 决策）：
   - 计划的 `skill_loader.load_skill_from_path(install_path, skill_name=...)` 方法不存在于 `SkillLoader`
   - `SkillLoader` 需要 `skills_dir` + `scan_and_register()` 扫目录模式，不支持任意 install_path 加载
   - 当前实现只遍历 servers_data 加载 MCP，skills_data 未处理（DEC-004 技术债）
   - handoff 标注 skill_loader.py 为 "只读参考"，plan 授权添加方法但有歧义 → 留主 agent 裁决
2. **`assembler.skills` 属性不存在**：plan Step 3d 末尾的 `assembler.skills = loaded_skill_infos` 无法执行 — `PromptAssembler` 没有 `skills` 属性，已省略该赋值
3. **stdio-only MCP bootstrap**：HTTP MCP servers 在 Step 3d-bis 中被跳过（`transport != "stdio"` 过滤），等待 W5（MCPClient HTTP transport）完成后再接入
4. W5 的 `executor/tests/test_mcp_client_http.py` 3 个测试仍 FAIL（MCPClient 尚无 transport 参数 — 预存在，非本任务）
