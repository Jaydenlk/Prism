# Prompt Caching 真集成 — 设计文档

> **日期**: 2026-05-09
> **优先级**: P0（PRD DOC-02 §3.1 核心能力）
> **状态**: approved

---

## 问题

`prompt_assembler.build()` 返回 `静态前缀 + CACHE_BOUNDARY_MARKER + 动态后缀` 单个字符串。`AnthropicDriver` 把整个字符串包成一个 `{"type": "text"}` block 加 `cache_control`。动态部分每轮都变，导致缓存永远命不中。

## 目标

静态前缀和动态后缀分成两个 system content block，`cache_control` 只加在静态前缀上。后续轮次静态前缀不变 → 缓存命中。

## 改动范围

**只改**: `executor/adapters/anthropic_driver.py`

**不改**:
- `prompt_assembler.py` — 已正确标记边界
- `query_engine.py` — 接口不变
- `base.py` / `openai_driver.py` — 接口不变
- 前端 — UsagePage 已展示 cache 数据

## 设计

### 1. system_prompt 拆分

`stream()` 和 `complete()` 中，按 `CACHE_BOUNDARY_MARKER` 拆分：

```python
from executor.engine.prompt_assembler import CACHE_BOUNDARY_MARKER

if CACHE_BOUNDARY_MARKER in system_prompt:
    static, dynamic = system_prompt.split(CACHE_BOUNDARY_MARKER, 1)
    system_blocks = [
        {"type": "text", "text": static},
        {"type": "text", "text": dynamic},
    ]
else:
    system_blocks = [{"type": "text", "text": system_prompt}]
```

### 2. cache_control 注入

`_inject_cache_control` 改为在**第一个** system text block 注入（静态前缀），而非最后一个：

```python
for block in system_blocks:
    if block.get("type") == "text":
        block["cache_control"] = {"type": "ephemeral"}
        break
```

用户消息断点保持不变（最后 user message 最后 text block）。

### 3. Cache Breakpoint 布局

| # | 位置 | 缓存效果 |
|---|---|---|
| 1 | system block 0（静态前缀，~9 sections） | 同 session 每轮命中 |
| 2 | 最后 user message 最后 text block | 多轮对话历史命中 |

最多 4 个断点，我们用 2 个。

### 4. Token 阈值

Sonnet 4.x = 2048，Opus 4.x = 4096。静态前缀 9 sections 通常远超阈值。低于阈值时 API 静默忽略，不报错。

## 验证

1. 真实 API 调用后 `response.usage.cache_read_input_tokens > 0`（第二轮起）
2. 前端 UsagePage cache 数据可见
3. 单元测试验证 split + 注入位置

## 官方文档参考

- Anthropic Prompt Caching docs（2026-05-09 WebFetch 确认）
- `cache_control: {"type": "ephemeral"}` 格式确认
- 多 system content block 支持确认
- 最大 4 breakpoints 限制确认
