# executor_v2 Audit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 14 audit findings — eliminate fake implementations, fix broken pipelines, harden for production.

**Architecture:** Three parallel groups: (A) foundation fixes, (B) hook hardening, (C) lifecycle restructure. Group C must run after A completes because it depends on the new registry.fire() behavior.

**Tech Stack:** Python 3.12, claude-agent-sdk, FastAPI, asyncio, Redis, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-05-13-executor-v2-integration-contracts.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `executor_v2/hooks/registry.py` | Modify | Inject `_event` into payload, remove 5 dead constants, fix callback type |
| `executor_v2/hooks/sdk_bridge.py` | Modify | Inject `_is_failure` for failure events, keyword-only `_event` |
| `executor_v2/runtime.py` | Modify | Accept `memory_prompt`, fix lifecycle, pass real exception to RUN_ERROR |
| `executor_v2/__main__.py` | Modify | Recall memories before runtime, pass as param |
| `executor_v2/hooks/memory_hook.py` | Modify | Remove prompt mutation, keep only extraction |
| `executor_v2/callbacks.py` | Modify | Redis PUBLISH resilience |
| `executor_v2/hooks/builtin/guardrail.py` | Rewrite | Split pre/post, fix path check |
| `executor_v2/hooks/builtin/safety.py` | Modify | Register on failure events, fix circuit breaker |
| `executor_v2/hooks/builtin/permission.py` | Rewrite | Configurable from env |
| `executor_v2/hooks/builtin/observability.py` | Rewrite | Structured logging with masking |
| `backend/app/api/v1/memories.py` | Modify | Fix IDOR, fix defaults, singleton |
| `backend/app/services/memory_service.py` | Modify | Add user_id to delete |

---

## Group A: Foundation Fixes (parallel, no dependencies)

### Task 1: Registry — inject `_event`, remove dead constants, fix types

**Files:**
- Modify: `executor_v2/hooks/registry.py`

- [ ] Remove 5 dead event constants: `TURN_START`, `TURN_END`, `THINKING_DELTA`, `TOOL_START`, `TOOL_END`

- [ ] In `fire()`, inject `_event` into payload before dispatching:
```python
async def fire(self, event: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    payload["_event"] = event
    handlers = self._handlers.get(event, [])
    # ... rest unchanged
```

- [ ] Fix `HookHandler.callback` type from `Callable[..., ...]` to:
```python
@dataclass
class HookHandler:
    callback: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    priority: int = 100
    category: str = "observability"
```

- [ ] Verify: `python -c "import py_compile; py_compile.compile('executor_v2/hooks/registry.py', doraise=True)"`

- [ ] Commit: `fix(hooks): registry injects _event, removes 5 dead constants, fixes callback type`

---

### Task 2: Callbacks — Redis PUBLISH resilience

**Files:**
- Modify: `executor_v2/callbacks.py`

- [ ] Wrap `text_delta` Redis PUBLISH in try/except:
```python
async def text_delta(self, text: str, message_id: str) -> None:
    payload = json.dumps({
        "type": "text_delta",
        "run_id": self._run_id,
        "session_id": self._session_id,
        "message_id": message_id,
        "text": text,
        "ts": self._now(),
    })
    try:
        await self._redis.publish(f"run:{self._run_id}:stream", payload)
    except Exception as exc:
        logger.warning("text_delta_publish_failed", error=str(exc))
```

- [ ] Verify syntax

- [ ] Commit: `fix(callbacks): Redis PUBLISH resilience for text_delta`

---

### Task 3: Memories API — fix IDOR, fix defaults, singleton service

**Files:**
- Modify: `backend/app/api/v1/memories.py`
- Modify: `backend/app/services/memory_service.py`

- [ ] Fix IDOR: `delete_memory` must verify ownership. Change `MemoryService.delete_memory` to accept `user_id`:
```python
# memory_service.py
async def delete_memory(self, user_id: str, memory_id: str) -> None:
    self._require_enabled()
    memories = await self._memory.get_all(filters={"user_id": user_id})
    owned_ids = {m.get("id") for m in (memories if isinstance(memories, list) else memories.get("results", []))}
    if memory_id not in owned_ids:
        raise HTTPException(status_code=404, detail="Memory not found")
    try:
        await self._memory.delete(memory_id=memory_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("memory.delete_failed", memory_id=memory_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Memory delete failed")
```

- [ ] Fix all `= None` defaults on `user` parameter — remove the default:
```python
# Change all instances of:
user: Annotated[User, Depends(get_current_user)] = None,
# To:
user: Annotated[User, Depends(get_current_user)],
```

- [ ] Fix delete endpoint to pass user_id:
```python
@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = MemoryService()
    await svc.delete_memory(str(user.id), memory_id)
```

- [ ] Verify syntax

- [ ] Commit: `fix(memories): IDOR on delete, remove = None defaults`

---

## Group B: Hook Hardening (parallel, depends on Task 1)

### Task 4: SDK Bridge — inject `_is_failure`, keyword-only `_event`

**Files:**
- Modify: `executor_v2/hooks/sdk_bridge.py`

- [ ] Make `_event` keyword-only to prevent accidental override:
```python
async def _callback(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
    *,
    _event: str = captured_event,
) -> dict[str, Any]:
```

- [ ] For `POST_TOOL_USE_FAILURE`, set `_is_failure=True` in payload:
```python
payload = dict(input_data)
if tool_use_id is not None:
    payload.setdefault("tool_use_id", tool_use_id)
if _event == POST_TOOL_USE_FAILURE:
    payload["_is_failure"] = True
```

- [ ] Verify syntax

- [ ] Commit: `fix(sdk_bridge): keyword-only _event, inject _is_failure for failures`

---

### Task 5: Guardrail — split pre/post, fix path check

**Files:**
- Rewrite: `executor_v2/hooks/builtin/guardrail.py`

- [ ] Split into two handlers: `pre_guardrail` (path check on PRE_TOOL_USE) and `post_guardrail` (content check on POST_TOOL_USE):

```python
from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

INVESTMENT_KEYWORDS: frozenset[str] = frozenset({
    "投资", "理财", "炒股", "基金推荐", "股票推荐",
    "buy stock", "investment advice",
})

WORKSPACE_PREFIX = os.environ.get("WORKSPACE_PATH", "/workspace")


async def pre_guardrail(payload: dict) -> dict:
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path", "command"):
        value = str(tool_input.get(key, ""))
        if not value:
            continue
        resolved = os.path.realpath(value)
        if not resolved.startswith(WORKSPACE_PREFIX) and not resolved.startswith("/tmp"):
            logger.warning("guardrail.path_blocked", path=value, resolved=resolved)
            return {
                "continue_": False,
                "decision": "block",
                "reason": f"Guardrail: path outside workspace — {value}",
            }
    return {"continue_": True}


async def post_guardrail(payload: dict) -> dict:
    response = str(payload.get("tool_response", "")).lower()
    for keyword in INVESTMENT_KEYWORDS:
        if keyword in response:
            return {
                "continue_": False,
                "decision": "block",
                "reason": "Guardrail: investment advice detected",
            }
    return {"continue_": True}
```

- [ ] Update `__main__.py` registration — pre on PRE_TOOL_USE, post on POST_TOOL_USE:
```python
from executor_v2.hooks.builtin.guardrail import pre_guardrail, post_guardrail

registry.register(PRE_TOOL_USE, HookHandler(callback=pre_guardrail, priority=20, category="guardrail"))
registry.register(POST_TOOL_USE, HookHandler(callback=post_guardrail, priority=20, category="guardrail"))
```

- [ ] Verify syntax

- [ ] Commit: `fix(guardrail): split pre/post, path check before execution`

---

### Task 6: Safety — fix circuit breaker, use deque

**Files:**
- Rewrite: `executor_v2/hooks/builtin/safety.py`

- [ ] Fix circuit breaker by reading `_is_failure` (now injected by SDKBridge). Use `collections.deque`:

```python
from __future__ import annotations

import hashlib
from collections import deque

import structlog

logger = structlog.get_logger(__name__)

LOOP_WINDOW = 10
LOOP_THRESHOLD = 3
FAILURE_THRESHOLD = 5


class SafetyState:
    def __init__(self) -> None:
        self.recent_calls: deque[str] = deque(maxlen=LOOP_WINDOW)
        self.consecutive_failures: int = 0


_state = SafetyState()


def _call_key(payload: dict) -> str:
    tool_name = payload.get("tool_name", "")
    tool_input = str(sorted(payload.get("tool_input", {}).items()))
    return hashlib.sha256(f"{tool_name}:{tool_input}".encode()).hexdigest()[:16]


async def safety_handler(payload: dict) -> dict:
    if payload.get("_is_failure", False):
        _state.consecutive_failures += 1
        logger.info("safety.failure", count=_state.consecutive_failures)
    else:
        _state.consecutive_failures = 0

    if _state.consecutive_failures >= FAILURE_THRESHOLD:
        logger.warning("safety.circuit_breaker", count=_state.consecutive_failures)
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Safety: circuit breaker — {_state.consecutive_failures} consecutive failures",
        }

    key = _call_key(payload)
    _state.recent_calls.append(key)

    if _state.recent_calls.count(key) >= LOOP_THRESHOLD:
        logger.warning("safety.loop_detected", tool=payload.get("tool_name"))
        return {
            "continue_": False,
            "decision": "block",
            "reason": "Safety: tool call loop detected",
        }

    return {"continue_": True}
```

- [ ] In `__main__.py`, register safety on BOTH POST_TOOL_USE and POST_TOOL_USE_FAILURE:
```python
registry.register(POST_TOOL_USE, HookHandler(callback=safety_handler, priority=30, category="safety"))
registry.register(POST_TOOL_USE_FAILURE, HookHandler(callback=safety_handler, priority=30, category="safety"))
```

- [ ] Verify syntax

- [ ] Commit: `fix(safety): circuit breaker works, deque for loop window`

---

### Task 7: Permission — configurable blocked tools

**Files:**
- Rewrite: `executor_v2/hooks/builtin/permission.py`

- [ ] Read blocked tools from env var:

```python
from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_raw = os.environ.get("PRISM_BLOCKED_TOOLS", "")
BLOCKED_TOOLS: frozenset[str] = frozenset(t.strip() for t in _raw.split(",") if t.strip())


async def permission_handler(payload: dict) -> dict:
    tool_name = payload.get("tool_name", "")
    if tool_name in BLOCKED_TOOLS:
        logger.warning("permission.blocked", tool=tool_name)
        return {
            "continue_": False,
            "decision": "block",
            "reason": f"Tool '{tool_name}' blocked by PRISM_BLOCKED_TOOLS policy",
        }
    return {"continue_": True}
```

- [ ] Verify syntax

- [ ] Commit: `fix(permission): configurable via PRISM_BLOCKED_TOOLS env var`

---

### Task 8: Observability — structured fields, masking

**Files:**
- Rewrite: `executor_v2/hooks/builtin/observability.py`

- [ ] Add structured fields and sensitive data masking:

```python
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SENSITIVE_KEYS = frozenset({"api_key", "token", "secret", "password", "authorization"})


def _mask_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            masked[k] = "***"
        elif isinstance(v, dict):
            masked[k] = _mask_sensitive(v)
        else:
            masked[k] = v
    return masked


async def observability_handler(payload: dict) -> dict:
    event = payload.get("_event", "unknown")
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    safe_input = _mask_sensitive(payload.get("tool_input", {})) if payload.get("tool_input") else None

    logger.info(
        "hook.event",
        event=event,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        tool_input=safe_input,
    )
    return {"continue_": True}
```

- [ ] Verify syntax

- [ ] Commit: `fix(observability): structured fields, sensitive data masking`

---

## Group C: Lifecycle Restructure (sequential, depends on Group A)

### Task 9: Memory hook — remove prompt mutation

**Files:**
- Rewrite: `executor_v2/hooks/memory_hook.py`

- [ ] Remove `on_session_start` (prompt mutation is broken by design). Keep only extraction on session end and message accumulation:

```python
from __future__ import annotations

import structlog

from executor_v2.hooks.registry import (
    HookHandler,
    HookRegistry,
    MESSAGE_COMPLETE,
    SESSION_END,
)
from executor_v2.userbrain.memory import MemoryManager

logger = structlog.get_logger(__name__)


class MemoryHook:
    def __init__(self, memory_manager: MemoryManager, user_id: str) -> None:
        self._memory = memory_manager
        self._user_id = user_id
        self._conversation_messages: list[dict] = []

    async def on_message_complete(self, payload: dict) -> dict:
        role = payload.get("role", "")
        blocks = payload.get("blocks", [])
        text_parts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text")]
        if role and text_parts:
            self._conversation_messages.append({"role": role, "content": " ".join(text_parts)})
        return {"continue_": True}

    async def on_session_end(self, payload: dict) -> dict:
        if self._conversation_messages:
            await self._memory.extract_and_store(self._user_id, self._conversation_messages)
            logger.info("memory_extracted", user_id=self._user_id, turns=len(self._conversation_messages))
        return {"continue_": True}

    def register(self, registry: HookRegistry) -> None:
        registry.register(MESSAGE_COMPLETE, HookHandler(callback=self.on_message_complete, priority=5, category="observability"))
        registry.register(SESSION_END, HookHandler(callback=self.on_session_end, priority=5, category="observability"))
```

- [ ] Verify syntax

- [ ] Commit: `fix(memory_hook): remove broken prompt mutation, extraction only`

---

### Task 10: Runtime + Main — fix lifecycle ordering

**Files:**
- Modify: `executor_v2/runtime.py`
- Modify: `executor_v2/__main__.py`

- [ ] **runtime.py**: Accept `memory_prompt: str` parameter. Inject into system_prompt at build time. Pass real exception to RUN_ERROR:

```python
class PrismAgentRuntime:
    def __init__(
        self,
        config: RunConfig,
        callback: BackendCallback,
        registry: HookRegistry,
        memory_prompt: str = "",
    ) -> None:
        self._config = config
        self._callback = callback
        self._registry = registry
        self._bridge = SDKBridge(registry)
        self._memory_prompt = memory_prompt
        self._client: ClaudeSDKClient | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        env: dict[str, str] = {"ANTHROPIC_API_KEY": self._config.api_key}
        if self._config.base_url:
            env["ANTHROPIC_BASE_URL"] = self._config.base_url

        # Combine base system_prompt + recalled memories
        combined = self._config.system_prompt
        if self._memory_prompt:
            combined = f"{combined}\n\n{self._memory_prompt}".strip() if combined else self._memory_prompt

        system_prompt: dict[str, Any] | None = None
        if combined:
            system_prompt = {
                "type": "preset",
                "preset": "claude_code",
                "append": combined,
            }

        return ClaudeAgentOptions(
            model=self._config.model,
            system_prompt=system_prompt,
            permission_mode="acceptEdits",
            max_turns=self._config.max_turns,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            env=env,
            include_partial_messages=True,
            hooks=self._bridge.build_sdk_hooks(),
        )
```

- [ ] Fix RUN_ERROR to pass real exception:
```python
except Exception as exc:
    log.exception("runtime_error")
    await self._registry.fire(RUN_ERROR, {
        "run_id": self._config.run_id,
        "error": str(exc),
    })
    raise
```

- [ ] **__main__.py**: Recall memories BEFORE creating runtime, pass as param. Remove unused import. Fix build_registry to not take config:

```python
async def main() -> None:
    args = parse_args()
    log = logger.bind(run_id=args.run_id)
    log.info("executor_v2.starting")

    config = load_run_config(args)

    callback = BackendCallback(
        callback_url=config.callback_url,
        callback_secret=config.callback_secret,
        run_id=config.run_id,
        session_id=config.session_id,
        redis_url=config.redis_url,
    )

    # Recall memories BEFORE runtime construction
    mem = MemoryManager()
    memories = await mem.recall(config.user_id, config.prompt)
    memory_prompt = mem.build_prompt_section(memories)

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        run_heartbeat(
            redis_url=config.redis_url,
            run_id=config.run_id,
            stop_event=stop_event,
            interval=int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "5")),
            ttl=int(os.environ.get("HEARTBEAT_TTL_SECONDS", "60")),
        )
    )

    registry = build_registry(callback, config.user_id)
    runtime = PrismAgentRuntime(config, callback, registry, memory_prompt=memory_prompt)
    # ... rest unchanged
```

- [ ] Update `build_registry` to take `user_id` instead of `config`:
```python
def build_registry(callback: BackendCallback, user_id: str) -> HookRegistry:
    registry = HookRegistry()
    prism = PrismHooks(callback)

    registry.register(PRE_TOOL_USE, HookHandler(callback=permission_handler, priority=10, category="permission"))
    registry.register(PRE_TOOL_USE, HookHandler(callback=pre_guardrail, priority=20, category="guardrail"))
    registry.register(PRE_TOOL_USE, HookHandler(callback=prism.on_pre_tool_use, priority=50, category="observability"))
    registry.register(POST_TOOL_USE, HookHandler(callback=post_guardrail, priority=20, category="guardrail"))
    registry.register(POST_TOOL_USE, HookHandler(callback=safety_handler, priority=30, category="safety"))
    registry.register(POST_TOOL_USE, HookHandler(callback=prism.on_post_tool_use, priority=50, category="observability"))
    registry.register(POST_TOOL_USE_FAILURE, HookHandler(callback=safety_handler, priority=30, category="safety"))
    registry.register(POST_TOOL_USE_FAILURE, HookHandler(callback=prism.on_post_tool_use_failure, priority=50, category="observability"))

    for event in [PRE_TOOL_USE, POST_TOOL_USE, POST_TOOL_USE_FAILURE]:
        registry.register(event, HookHandler(callback=observability_handler, priority=999, category="observability"))

    memory_hook = MemoryHook(MemoryManager(), user_id)
    memory_hook.register(registry)

    return registry
```

- [ ] Verify syntax for both files

- [ ] Commit: `fix(lifecycle): memory recall before SDK init, real exceptions in RUN_ERROR`

---

## Verification

After all tasks complete:

- [ ] `python -c "import py_compile; [py_compile.compile(f'executor_v2/{f}', doraise=True) for f in ['__init__.py','__main__.py','config.py','callbacks.py','heartbeat.py','runtime.py','hooks/__init__.py','hooks/registry.py','hooks/sdk_bridge.py','hooks/prism_hook.py','hooks/memory_hook.py','hooks/builtin/__init__.py','hooks/builtin/permission.py','hooks/builtin/guardrail.py','hooks/builtin/safety.py','hooks/builtin/observability.py','userbrain/__init__.py','userbrain/memory.py']]"`
- [ ] `python -c "import py_compile; py_compile.compile('backend/app/api/v1/memories.py', doraise=True); py_compile.compile('backend/app/services/memory_service.py', doraise=True)"`
- [ ] Docker rebuild + integration test: submit task with tool use → verify tool_start callback + observability logs show real event names
- [ ] Verify guardrail blocks path outside workspace on PRE_TOOL_USE (before execution)
