# Handoff: main → implementer (W9 / SearXNG self-hosted + drop Brave)

## 状态: READY_FOR_IMPL

## 任务描述
2 件事：
1. 加 SearXNG 自托管搜索引擎为 docker compose service + 注册为 system MCP（stdio via `npx -y mcp-searxng`）
2. 删 Brave Search builtin 条目（2026-02 起 Brave 取消免费层，留 builtin 会误导用户）

## 输入文件范围（仅这些）
- 修改: `docker-compose.yml` 加 searxng 服务（searxng/searxng image，默认 8080 内部端口；env 注入；volume `./searxng:/etc/searxng`）
- 创建: `searxng/settings.yml`（最小化配置：启用 google/bing/duckduckgo engines + JSON output format + 关闭 limiter）
- 修改: `backend/app/services/mcp_service.py` `_BUILTIN_MCP_SERVERS`：
  - 删除 `brave-search` 条目（整个 dict）
  - 追加 `searxng` 条目（stdio, command=`npx`, args=`["-y", "mcp-searxng"]`, env_var=`SEARXNG_URL`, env 拼一个 `SEARXNG_URL=http://searxng:8080`）— **特殊**: searxng 没有 API key 概念, env_var 字段命名仅用于 gate；可以直接 hardcoded env 不依赖 env_var 也成
- 修改: `backend/tests/test_mcp_builtin_stdio.py`：
  - 删 `test_brave_in_builtins`、`test_register_skips_brave_if_no_key`、`test_register_creates_brave_if_key_set`
  - 加 `test_searxng_in_builtins`、`test_register_creates_searxng_unconditionally` (因 SEARXNG_URL 总是有默认值)
- 只读参考:
  - 现有 `_BUILTIN_MCP_SERVERS` 看 dict 结构
  - https://hub.docker.com/r/searxng/searxng （image config）
  - https://github.com/ihor-sokoliuk/mcp-searxng（npm package 的 env 协议 — `SEARXNG_URL` 是默认 env）

## 禁止触碰
- 任何 frontend 文件
- 任何 executor 文件
- backend 其他文件（tests 除外）
- alembic / models / schemas
- 工具源码 / __init__.py
- `start.sh`（主 agent 后续更新文档）

## 产出预期
- 新增 searxng container 启动后内部 8080 可达（`docker exec prismv3-searxng-1 curl localhost:8080/healthz` 应返 200）
- `_BUILTIN_MCP_SERVERS` 中无 brave 条目，有 searxng 条目
- backend 测试通过（mcp_service tests 调整后全 PASS）
- 完成后回填 handoff 状态

## 决策上下文
- Brave 2026-02 起从免费转付费（要 CC + 月 $5 起）— 弃用
- SearXNG 自托管：开源 / 0 成本 / 无限查询 / 聚合 251 个搜索源 / 私密
- mcp-searxng 是社区 npm package（不是 Anthropic 官方），但 stdio 模式简单，故障域小
- 工作树: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`
- searxng 镜像建议：`searxng/searxng:latest` （compose 里也可以 pin 具体版本）

## 已完成
（implementer 完成后填）

## 产出物
（implementer 完成后填）

## 遗留问题
（如有）
