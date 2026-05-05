# Handoff: main → implementer (W8 / Action Tools Tests)

## 状态: READY_FOR_IMPL

## 任务描述
为 7 个新内置 action tool 写完整 unit tests（happy path + error path）。工具源码已就绪在 `executor/tools/builtin/`。

## 输入文件范围（仅这些）
- 创建: `executor/tests/test_action_tools.py`（一个文件覆盖 7 个工具，按 class 分组）
- 只读参考:
  - `executor/tools/base.py` (BaseTool / ToolResult API)
  - `executor/tools/builtin/read.py` `write.py` `edit.py` `bash.py` `glob.py` `grep.py` `web_fetch.py`
  - 现有 `executor/tests/test_skill_register_from_path.py` 学风格

## 禁止触碰
- 任何 backend / frontend 文件
- 工具源码（只读，不改）
- `executor/tools/builtin/__init__.py`（主 agent 已改）
- `executor/__main__.py`（主 agent 已改）
- 现有测试文件

## 产出预期
- `test_action_tools.py` 文件
- 覆盖每个工具至少：1 个 happy + 2 个 error/edge case
- 使用 `tmp_path` fixture 处理 Read/Write/Edit/Glob/Grep
- Bash 用真实 shell 命令测（echo / sleep / exit 1）
- WebFetch 用 `respx.mock` 模拟（项目已有 respx）
- 全部 PASS（`pytest executor/tests/test_action_tools.py -v`）
- 完成后回填 handoff 状态 `READY_FOR_IMPL → READY_FOR_REVIEW`

## 决策上下文
- DEC-006: 工具操作在 executor 容器 fs 内，无路径白名单（依赖容器隔离）
- Read 默认 limit=2000，max 10000；返回 cat -n 风格行号前缀
- Edit 默认 unique-match，replace_all=true 时全替换
- Bash 默认 timeout 60s，max 600s；返合并 stdout+stderr，超 64KiB 截断
- Glob 按 mtime 排序（newest first），max 1000 结果
- Grep 优先用 rg（如 PATH 有），fallback Python regex
- WebFetch 30s timeout，5MiB 上限，HTML 自动 strip 标签
- 工作树: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
（implementer 完成后填）

## 产出物
（implementer 完成后填）

## 遗留问题
（如有）
