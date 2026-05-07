# Prompt Caching 真集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AnthropicDriver 按 CACHE_BOUNDARY_MARKER 将 system_prompt 拆成静态/动态两个 content block，cache_control 只注入静态前缀，实现真正的 Prompt Cache 命中。

**Architecture:** prompt_assembler 已用 `CACHE_BOUNDARY_MARKER` 标记静态/动态分界。Driver 解析此标记拆分为两个 system block，第一个（静态前缀）注入 `cache_control: {"type": "ephemeral"}`，第二个（动态后缀）不注入。用户消息断点保持不变。

**Tech Stack:** Python 3.11+ / httpx / Anthropic Messages API

---

## File Map

| 文件 | 操作 | 职责 |
|---|---|---|
| `executor/adapters/anthropic_driver.py` | Modify | 拆分 system_prompt + 修改 cache_control 注入逻辑 |
| `executor/tests/test_anthropic_cache.py` | Create | 测试 split + 注入逻辑 |

---

### Task 1: 测试先行 — cache_control 注入位置验证

**Files:**
- Create: `executor/tests/test_anthropic_cache.py`

- [ ] **Step 1: 写失败测试 — 带 CACHE_BOUNDARY_MARKER 时拆成两个 system block**

```python
"""AnthropicDriver prompt cache integration tests."""

from __future__ import annotations

from executor.adapters.anthropic_driver import AnthropicDriver
from executor.adapters.base import ProviderCapabilities
from executor.engine.prompt_assembler import CACHE_BOUNDARY_MARKER


def _make_driver(prompt_cache: bool = True) -> AnthropicDriver:
    caps = ProviderCapabilities(prompt_cache=prompt_cache)
    return AnthropicDriver(
        base_url="https://api.anthropic.com",
        api_key="test-key",
        model="claude-sonnet-4-20250514",
        capabilities=caps,
    )


class TestBuildSystemBlocks:
    """_build_system_blocks 拆分逻辑。"""

    def test_splits_at_cache_boundary_marker(self):
        driver = _make_driver()
        prompt = f"STATIC PREFIX{CACHE_BOUNDARY_MARKER}DYNAMIC SUFFIX"
        blocks = driver._build_system_blocks(prompt)
        assert len(blocks) == 2
        assert blocks[0] == {"type": "text", "text": "STATIC PREFIX"}
        assert blocks[1] == {"type": "text", "text": "DYNAMIC SUFFIX"}

    def test_no_marker_single_block(self):
        driver = _make_driver()
        prompt = "NO MARKER HERE"
        blocks = driver._build_system_blocks(prompt)
        assert len(blocks) == 1
        assert blocks[0] == {"type": "text", "text": "NO MARKER HERE"}

    def test_empty_dynamic_still_two_blocks(self):
        driver = _make_driver()
        prompt = f"STATIC ONLY{CACHE_BOUNDARY_MARKER}"
        blocks = driver._build_system_blocks(prompt)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "STATIC ONLY"

    def test_multiple_markers_split_at_first(self):
        driver = _make_driver()
        prompt = f"A{CACHE_BOUNDARY_MARKER}B{CACHE_BOUNDARY_MARKER}C"
        blocks = driver._build_system_blocks(prompt)
        assert len(blocks) == 2
        assert blocks[0]["text"] == "A"
        assert blocks[1]["text"] == f"B{CACHE_BOUNDARY_MARKER}C"


class TestInjectCacheControl:
    """_inject_cache_control 注入位置。"""

    def test_cache_control_on_first_system_block(self):
        driver = _make_driver()
        system_blocks = [
            {"type": "text", "text": "static"},
            {"type": "text", "text": "dynamic"},
        ]
        messages: list[dict] = []
        result_sys, _ = driver._inject_cache_control(system_blocks, messages)
        assert result_sys[0].get("cache_control") == {"type": "ephemeral"}
        assert "cache_control" not in result_sys[1]

    def test_cache_control_on_last_user_msg(self):
        driver = _make_driver()
        system_blocks = [{"type": "text", "text": "sys"}]
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
        ]
        _, result_msgs = driver._inject_cache_control(system_blocks, messages)
        last_user = result_msgs[2]
        assert last_user["content"][0].get("cache_control") == {"type": "ephemeral"}
        first_user = result_msgs[0]
        assert "cache_control" not in first_user["content"][0]

    def test_single_system_block_still_gets_cache_control(self):
        driver = _make_driver()
        system_blocks = [{"type": "text", "text": "only block"}]
        messages: list[dict] = []
        result_sys, _ = driver._inject_cache_control(system_blocks, messages)
        assert result_sys[0].get("cache_control") == {"type": "ephemeral"}

    def test_no_user_messages_only_system_cached(self):
        driver = _make_driver()
        system_blocks = [
            {"type": "text", "text": "static"},
            {"type": "text", "text": "dynamic"},
        ]
        messages: list[dict] = []
        result_sys, result_msgs = driver._inject_cache_control(system_blocks, messages)
        assert result_sys[0].get("cache_control") == {"type": "ephemeral"}
        assert result_msgs == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd executor && python -m pytest tests/test_anthropic_cache.py -v`
Expected: FAIL — `AttributeError: 'AnthropicDriver' object has no attribute '_build_system_blocks'`

- [ ] **Step 3: Commit 测试**

```bash
git add executor/tests/test_anthropic_cache.py
git commit -m "test: add failing tests for prompt cache split + injection"
```

---

### Task 2: 实现 — _build_system_blocks + 修改 _inject_cache_control

**Files:**
- Modify: `executor/adapters/anthropic_driver.py:161-189`（`_inject_cache_control`）
- Modify: `executor/adapters/anthropic_driver.py:217`（`stream()` 内 system_blocks 构建）
- Modify: `executor/adapters/anthropic_driver.py:438`（`complete()` 内 system_blocks 构建）

- [ ] **Step 1: 添加 _build_system_blocks 方法**

在 `_inject_cache_control` 之前添加：

```python
def _build_system_blocks(self, system_prompt: str) -> list[dict]:
    """将 system_prompt 按 CACHE_BOUNDARY_MARKER 拆分为多个 text block。

    静态前缀和动态后缀分离后，Driver 可以只在静态前缀上注入 cache_control，
    确保 Anthropic Prompt Cache 命中（静态前缀每轮字节级一致）。
    """
    from executor.engine.prompt_assembler import CACHE_BOUNDARY_MARKER

    if CACHE_BOUNDARY_MARKER in system_prompt:
        static, dynamic = system_prompt.split(CACHE_BOUNDARY_MARKER, 1)
        blocks = [{"type": "text", "text": static}]
        if dynamic.strip():
            blocks.append({"type": "text", "text": dynamic})
        return blocks
    return [{"type": "text", "text": system_prompt}]
```

- [ ] **Step 2: 修改 _inject_cache_control — 正序遍历注入第一个 text block**

将 `_inject_cache_control` 中 system 部分的 `reversed` 改为正序：

```python
def _inject_cache_control(
    self,
    system_blocks: list[dict],
    messages: list[dict],
) -> tuple[list[dict], list[dict]]:
    """注入 cache_control（ADR-008）。

    策略：
    1. system 第一个 text block 加 cache_control（静态前缀，字节级一致）
    2. 最后一条 user message 的最后一个 text block 加 cache_control
    """
    if system_blocks:
        for block in system_blocks:
            if block.get("type") == "text":
                block["cache_control"] = {"type": "ephemeral"}
                break

    for msg in reversed(messages):
        if msg["role"] == "user":
            for block in reversed(msg["content"]):
                if isinstance(block, dict) and block.get("type") == "text":
                    block["cache_control"] = {"type": "ephemeral"}
                    break
            break

    return system_blocks, messages
```

- [ ] **Step 3: 修改 stream() — 用 _build_system_blocks 替换单 block 构建**

`executor/adapters/anthropic_driver.py` 的 `stream()` 方法中，将：
```python
system_blocks: list[dict] = [{"type": "text", "text": system_prompt}]
```
替换为：
```python
system_blocks = self._build_system_blocks(system_prompt)
```

- [ ] **Step 4: 修改 complete() — 同样替换**

`executor/adapters/anthropic_driver.py` 的 `complete()` 方法中，将：
```python
system_blocks: list[dict] = [{"type": "text", "text": system_prompt}]
```
替换为：
```python
system_blocks = self._build_system_blocks(system_prompt)
```

- [ ] **Step 5: 运行测试确认全部通过**

Run: `cd executor && python -m pytest tests/test_anthropic_cache.py -v`
Expected: 8 tests PASS

- [ ] **Step 6: 运行全量 executor 测试确认无回归**

Run: `cd executor && python -m pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add executor/adapters/anthropic_driver.py
git commit -m "feat: split system_prompt at CACHE_BOUNDARY_MARKER for real prompt cache hits"
```

---

### Task 3: 验证 — 全量测试 + 文档注释清理

- [ ] **Step 1: 运行 backend + executor 全量测试**

Run: `cd backend && python -m pytest tests/ -v && cd ../executor && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: 清理 _inject_cache_control 上方过时注释**

确认 docstring 和内联注释与新逻辑一致（"第一个 text block" 而非 "最后一个"）。

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "docs: update cache_control injection comments to match new split logic"
```
