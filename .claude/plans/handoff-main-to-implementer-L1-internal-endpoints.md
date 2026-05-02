# Handoff: main → implementer (Task 1 / W1 / L1)

## 状态: READY_FOR_REVIEW

## 任务描述
为 executor 启动期 plugin bootstrap 加 backend 的 2 个 internal endpoints。

## 输入文件范围（仅这些）
- 修改: `backend/app/api/v1/internal.py` (在现有 router 上扩展，不要重写)
- 创建: `backend/tests/test_internal_plugin_endpoints.py`
- 修改: `backend/tests/conftest.py` (加 fixtures，如已存在 client/db fixture 则复用)
- 只读参考:
  - `backend/app/models/skill_install.py`
  - `backend/app/models/mcp_server.py`
  - `backend/app/core/security.py` (decrypt_value 函数)
  - `backend/app/core/config.py` (settings.CALLBACK_SECRET / ENCRYPTION_KEY)

## 禁止触碰
- 任何 frontend 文件
- 任何 executor 文件
- backend 其他 API 文件 (auth, sessions, runs, im, mcp, providers, admin 等)
- alembic migration 目录（schema 改动是 W4 的事）
- `.claude/memory/decisions.md`

## 产出预期
- 实现 plan 文件 `docs/superpowers/plans/2026-05-02-plugin-bootstrap.md` 中 **Task 1** 的全部 5 步
- 测试 6/6 PASS（如 `seeded_user_with_http_mcp` 因 W4 schema 未到位需 skip，明确标注）
- commit message 按 plan 提供
- 完成后更新本 handoff 文件状态：`READY_FOR_IMPL` → `READY_FOR_REVIEW`，并填"已完成"+"产出物"+"遗留问题"段落

## 决策上下文
- DEC-004: HTTP server 存 `headers_encrypted` (AES-256-GCM ciphertext)，本 endpoint 必须解密返明文给 executor
- DEC-004: ENCRYPTION_KEY 不进 executor (进程边界=信任边界硬底线)
- 复用现有 `_verify_callback_secret` Depends (file 已有)，不要改动 callback secret 验证逻辑
- 如 W4 schema 未到位，schema 字段访问用 `getattr(server, 'transport', 'stdio')` 兜底（plan 已注明）
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap` — 所有 git/pytest 命令必须在此目录执行

## 已完成
- 在 `backend/app/api/v1/internal.py` 新增 2 个 GET endpoints（`/users/{uid}/installed-skills` 和 `/users/{uid}/mcp-servers`）
- 在 `backend/tests/conftest.py` 扩展：StaticPool SQLite 测试基础设施（`db`、`client` fixtures）+ `callback_secret`、`seeded_user_with_mcp`、`seeded_user_with_http_mcp`、`seeded_user_with_skill` fixtures
- 创建 `backend/tests/test_internal_plugin_endpoints.py` 6 个测试
- 测试结果：5 pass / 1 skipped（`test_installed_skills_returns_user_skills`，原因见遗留问题）
- commit: 6072474

## 产出物
- `backend/app/api/v1/internal.py`: 新增 imports（json, decrypt_value, McpServer/UserMcpInstall, SkillInstall）+ 2 endpoints（lines ~225–310）
- `backend/tests/test_internal_plugin_endpoints.py`: 6 tests（含 2 skipif guards）
- `backend/tests/conftest.py`: 新增 StaticPool + 5 fixtures（db/client/callback_secret/seeded_user_with_mcp/seeded_user_with_http_mcp/seeded_user_with_skill）

## 遗留问题
- `test_installed_skills_returns_user_skills` 被 skipif 跳过。原因：`SkillInstall` model 当前没有 `status` 字段（Task 4 schema 才添加），`seeded_user_with_skill` fixture 无法创建带 `status` 的 SkillInstall 行。`McpServer.transport/url/headers_encrypted` 已经在 model 中（所以 http_mcp test 正常 PASS），但 `SkillInstall.status/install_path` 尚未在 model 或 migration 中出现。Task 4 schema 合并后，需要：1) 去掉 `test_installed_skills_returns_user_skills` 上的 skipif；2) 用直接属性访问替换 `getattr(r, 'install_path', None)`；3) `seeded_user_with_skill` 可直接传 `status="installed"` 和 `install_path`。
