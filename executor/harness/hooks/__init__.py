"""
executor.harness.hooks - Hook System public exports

Exports:
- HookEventType / HookEvent
- HookDecision / merge_decisions (ADR-026/027)
- HookHandlerConfig / HookHandlerExecutor
- HookSystem
"""

from executor.harness.hooks.decision import HookDecision, PermissionDecision, merge_decisions
from executor.harness.hooks.events import HookEvent, HookEventType
from executor.harness.hooks.handlers import HookHandlerConfig, HookHandlerExecutor
from executor.harness.hooks.system import HookSystem

__all__ = [
    "HookEventType",
    "HookEvent",
    "HookDecision",
    "PermissionDecision",
    "merge_decisions",
    "HookHandlerConfig",
    "HookHandlerExecutor",
    "HookSystem",
]
