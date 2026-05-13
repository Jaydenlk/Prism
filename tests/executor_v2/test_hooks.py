import importlib
import os
import sys

import pytest


@pytest.mark.asyncio
async def test_safety_loop_detection():
    import executor_v2.hooks.builtin.safety as safety_mod
    safety_mod._state.recent_calls.clear()
    safety_mod._state.consecutive_failures = 0

    payload = {"tool_name": "Bash", "tool_input": {"command": "echo"}}
    for _ in range(2):
        r = await safety_mod.safety_handler(payload)
        assert r["continue_"] is True
    r = await safety_mod.safety_handler(payload)
    assert r.get("decision") == "block"


@pytest.mark.asyncio
async def test_safety_circuit_breaker():
    import executor_v2.hooks.builtin.safety as safety_mod
    safety_mod._state.recent_calls.clear()
    safety_mod._state.consecutive_failures = 0

    # Use distinct tool names to avoid loop detection (same key 3x triggers loop).
    for i in range(4):
        payload = {"_is_failure": True, "tool_name": f"Tool{i}", "tool_input": {}}
        r = await safety_mod.safety_handler(payload)
        assert r["continue_"] is True
    payload = {"_is_failure": True, "tool_name": "Tool4", "tool_input": {}}
    r = await safety_mod.safety_handler(payload)
    assert r.get("decision") == "block"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="os.path.realpath converts Unix paths on Windows")
async def test_guardrail_blocks_outside_workspace():
    os.environ["WORKSPACE_PATH"] = "/workspace"
    import executor_v2.hooks.builtin.guardrail as guardrail_mod
    importlib.reload(guardrail_mod)

    r = await guardrail_mod.pre_guardrail(
        {"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}
    )
    assert r.get("decision") == "block"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="os.path.realpath converts Unix paths on Windows")
async def test_guardrail_allows_workspace_path():
    os.environ["WORKSPACE_PATH"] = "/workspace"
    import executor_v2.hooks.builtin.guardrail as guardrail_mod
    importlib.reload(guardrail_mod)

    r = await guardrail_mod.pre_guardrail(
        {"tool_name": "Read", "tool_input": {"file_path": "/workspace/main.py"}}
    )
    assert r["continue_"] is True


@pytest.mark.asyncio
async def test_guardrail_skips_bash():
    import executor_v2.hooks.builtin.guardrail as guardrail_mod

    r = await guardrail_mod.pre_guardrail(
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
    )
    assert r["continue_"] is True


@pytest.mark.asyncio
async def test_permission_empty_by_default():
    os.environ.pop("PRISM_BLOCKED_TOOLS", None)
    import executor_v2.hooks.builtin.permission as perm_mod
    importlib.reload(perm_mod)

    r = await perm_mod.permission_handler({"tool_name": "Bash"})
    assert r["continue_"] is True


@pytest.mark.asyncio
async def test_observability_masks_secrets():
    from executor_v2.hooks.builtin.observability import _mask_sensitive

    data = {"api_key": "sk-secret", "name": "safe", "nested": {"token": "abc"}}
    masked = _mask_sensitive(data)
    assert masked["api_key"] == "***"
    assert masked["name"] == "safe"
    assert masked["nested"]["token"] == "***"
