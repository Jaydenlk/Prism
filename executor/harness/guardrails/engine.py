"""
GuardrailsEngine — 声明式护栏规则引擎

平台级规则硬编码（不可被用户/插件覆盖）。
插件级规则随 Plugin 加载（DOC-05 实现）。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import structlog

from executor.harness.guardrails.rules import GuardrailRule
from executor.harness.permissions.result import PermissionResult

logger = structlog.get_logger()


class GuardrailsEngine:
    """声明式护栏规则引擎"""

    def __init__(self) -> None:
        self._rules: list[GuardrailRule] = []
        self._load_platform_rules()

    def _load_platform_rules(self) -> None:
        """加载平台级内置规则（GR-PLATFORM-001 ~ 004）"""
        from executor.harness.guardrails.platform_rules import get_platform_rules
        platform_rules = get_platform_rules()
        self._rules.extend(platform_rules)
        logger.info(
            "harness.guardrails.platform_rules_loaded",
            count=len(platform_rules),
        )

    def add_rule(self, rule: GuardrailRule) -> None:
        """追加自定义规则（插件级，DOC-05 使用）"""
        self._rules.append(rule)

    def check(
        self,
        tool_name: str,
        tool_input: dict,
        run_context=None,
    ) -> PermissionResult:
        """对工具调用做确定性规则检查。O(rules) 复杂度，ms 级。

        返回 PermissionResult：
        - decision="deny" 若任一规则匹配
        - decision="allow" 若全部规则通过
        """
        for rule in self._rules:
            if rule.matches(tool_name, tool_input, run_context):
                logger.info(
                    "harness.guardrails.deny",
                    rule_id=rule.id,
                    tool_name=tool_name,
                    reason=rule.reason,
                )
                try:
                    from executor.observability.metrics import prism_guardrail_deny_total
                    prism_guardrail_deny_total.labels(rule_id=rule.id).inc()
                except Exception:
                    pass  # metrics 降级不影响主路径
                return PermissionResult(decision="deny", reason=rule.reason)
        return PermissionResult(decision="allow")
