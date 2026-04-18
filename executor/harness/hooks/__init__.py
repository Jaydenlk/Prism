"""
executor.harness.hooks - Hook System public exports

Exports:
- HookEventType / HookEvent / PHASE1_EVENTS / PHASE2_EVENTS (ADR-048)
- HookDecision / merge_decisions (ADR-026/027)
- HookHandlerConfig / HookHandlerExecutor
- HookSystem (优先级排序 + scoped 注销, ADR-048)
"""

from executor.harness.hooks.decision import HookDecision, PermissionDecision, merge_decisions
from executor.harness.hooks.events import PHASE1_EVENTS, PHASE2_EVENTS, HookEvent, HookEventType
from executor.harness.hooks.handlers import HookHandlerConfig, HookHandlerExecutor
from executor.harness.hooks.system import HookSystem

__all__ = [
    "HookEventType",
    "HookEvent",
    "PHASE1_EVENTS",
    "PHASE2_EVENTS",
    "HookDecision",
    "PermissionDecision",
    "merge_decisions",
    "HookHandlerConfig",
    "HookHandlerExecutor",
    "HookSystem",
]
