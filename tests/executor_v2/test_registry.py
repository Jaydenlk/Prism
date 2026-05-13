import pytest


@pytest.mark.asyncio
async def test_fire_injects_event_name():
    from executor_v2.hooks.registry import HookRegistry, HookHandler

    registry = HookRegistry()
    received = {}

    async def handler(payload):
        received.update(payload)
        return {"continue_": True}

    registry.register("TestEvent", HookHandler(callback=handler))
    await registry.fire("TestEvent", {"foo": "bar"})
    assert received["_event"] == "TestEvent"
    assert received["foo"] == "bar"


@pytest.mark.asyncio
async def test_priority_ordering():
    from executor_v2.hooks.registry import HookRegistry, HookHandler

    registry = HookRegistry()
    order = []

    async def h1(p):
        order.append(1)
        return {"continue_": True}

    async def h2(p):
        order.append(2)
        return {"continue_": True}

    async def h3(p):
        order.append(3)
        return {"continue_": True}

    registry.register("E", HookHandler(callback=h3, priority=300))
    registry.register("E", HookHandler(callback=h1, priority=100))
    registry.register("E", HookHandler(callback=h2, priority=200))
    await registry.fire("E", {})
    assert order == [1, 2, 3]


@pytest.mark.asyncio
async def test_blocking_short_circuit():
    from executor_v2.hooks.registry import HookRegistry, HookHandler

    registry = HookRegistry()
    reached = []

    async def blocker(p):
        reached.append("blocker")
        return {"continue_": False, "decision": "block"}

    async def after(p):
        reached.append("after")
        return {"continue_": True}

    registry.register("E", HookHandler(callback=blocker, priority=10, category="guardrail"))
    registry.register("E", HookHandler(callback=after, priority=20, category="observability"))
    await registry.fire("E", {})
    assert reached == ["blocker"]


@pytest.mark.asyncio
async def test_observability_error_swallowed():
    from executor_v2.hooks.registry import HookRegistry, HookHandler

    registry = HookRegistry()

    async def bad(p):
        raise ValueError("boom")

    async def good(p):
        return {"continue_": True}

    registry.register("E", HookHandler(callback=bad, priority=10, category="observability"))
    registry.register("E", HookHandler(callback=good, priority=20, category="observability"))
    results = await registry.fire("E", {})
    assert len(results) == 1
