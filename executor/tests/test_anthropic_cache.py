"""AnthropicDriver prompt cache integration tests.

Validates that system_prompt is split at CACHE_BOUNDARY_MARKER into
static (cached) and dynamic (uncached) system content blocks.
"""

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

    def test_splits_at_cache_boundary_marker(self):
        driver = _make_driver()
        prompt = f"STATIC PREFIX{CACHE_BOUNDARY_MARKER}DYNAMIC SUFFIX"
        blocks = driver._build_system_blocks(prompt)
        assert len(blocks) == 2
        assert blocks[0] == {"type": "text", "text": "STATIC PREFIX"}
        assert blocks[1] == {"type": "text", "text": "DYNAMIC SUFFIX"}

    def test_no_marker_single_block(self):
        driver = _make_driver()
        blocks = driver._build_system_blocks("NO MARKER HERE")
        assert len(blocks) == 1
        assert blocks[0] == {"type": "text", "text": "NO MARKER HERE"}

    def test_empty_dynamic_produces_single_block(self):
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

    def test_cache_control_on_first_system_block(self):
        driver = _make_driver()
        system_blocks = [
            {"type": "text", "text": "static"},
            {"type": "text", "text": "dynamic"},
        ]
        result_sys, _ = driver._inject_cache_control(system_blocks, [])
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
        assert result_msgs[2]["content"][0].get("cache_control") == {"type": "ephemeral"}
        assert "cache_control" not in result_msgs[0]["content"][0]

    def test_single_system_block_gets_cache_control(self):
        driver = _make_driver()
        system_blocks = [{"type": "text", "text": "only block"}]
        result_sys, _ = driver._inject_cache_control(system_blocks, [])
        assert result_sys[0].get("cache_control") == {"type": "ephemeral"}

    def test_no_user_messages_only_system_cached(self):
        driver = _make_driver()
        system_blocks = [
            {"type": "text", "text": "static"},
            {"type": "text", "text": "dynamic"},
        ]
        result_sys, result_msgs = driver._inject_cache_control(system_blocks, [])
        assert result_sys[0].get("cache_control") == {"type": "ephemeral"}
        assert result_msgs == []
