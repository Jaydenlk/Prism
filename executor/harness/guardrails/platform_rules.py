"""
平台级内置护栏规则

这些规则全局生效，不可被插件或用户覆盖。
对标 DOC-00 v4 §7 四条铁律的 Harness 强制层。

v4 补齐 4 类规则：
1. 破坏性操作（rm / DROP / DELETE 全表 / FORMAT / mkfs）— GR-PLATFORM-001
2. PII 检测（api_key/secret/password/token 明文进入 tool_input）— GR-PLATFORM-002
3. 速率限制（单 run 同工具 >N 次/分钟）— GR-PLATFORM-003
4. 跨用户访问（tool_input 中用户 ID 与 run 的 user_id 不一致）— GR-PLATFORM-004

_rate_window：module-level dict，跨进程不共享（每个 executor subprocess 独立状态，够用）。

进程边界：本模块只 import 标准库 + executor.harness.guardrails.rules，禁止 import backend.app.*
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque

from executor.harness.guardrails.rules import GuardrailRule

# ---------------------------------------------------------------------------
# 1. 破坏性操作 patterns
# ---------------------------------------------------------------------------
DANGEROUS_PATTERNS = [
    # Shell 破坏性命令
    r"rm\s+(-rf?|--recursive)",
    r"DROP\s+(TABLE|DATABASE)",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",  # 无 WHERE 的全表删除
    r"TRUNCATE\s+TABLE",
    r"FORMAT\s+",
    r"mkfs\.",
    r":\(\)\s*\{.*\};.*:\|:",         # fork bomb
    r">\s*/dev/sd[a-z]",              # 写 raw device
]

# ---------------------------------------------------------------------------
# 2. PII / 明文凭据 patterns
# ---------------------------------------------------------------------------
PII_PATTERNS = [
    r"(api[-_]?key|secret|password|token|bearer)\s*[:=]\s*[\"']?[\w\-\.]{16,}",
    r"\b[A-Z0-9]{20,}\b",              # AWS Key 形式
    r"sk-[A-Za-z0-9]{32,}",           # OpenAI Key 形式
    r"\bghp_[A-Za-z0-9]{20,}\b",      # GitHub PAT
]

# ---------------------------------------------------------------------------
# 3. 速率限制配置
# ---------------------------------------------------------------------------
# module-level dict，每个子进程独立（不跨进程共享，单 executor 子进程够用）
_rate_window: dict[tuple[str, str], deque] = defaultdict(deque)
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_PER_TOOL: dict[str, int] = {
    # 默认 30 次/分钟；特定工具有更低阈值
    "bash": 20,
    "Bash": 20,
    "Write": 50,
    "WebFetch": 10,
    "WebSearch": 10,
}
RATE_LIMIT_DEFAULT = 30


# ---------------------------------------------------------------------------
# 自定义匹配函数
# ---------------------------------------------------------------------------

def _rate_limit_check(tool_name: str, tool_input: dict, run_context) -> bool:
    """返回 True 表示触发限流（deny）"""
    if run_context is None:
        return False
    run_id = getattr(run_context, "run_id", None)
    if not run_id:
        return False
    limit = RATE_LIMIT_PER_TOOL.get(tool_name, RATE_LIMIT_DEFAULT)
    key = (run_id, tool_name)
    now = time.monotonic()
    window = _rate_window[key]
    # 清除过期记录
    while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    window.append(now)
    return len(window) > limit


def _cross_user_check(tool_name: str, tool_input: dict, run_context) -> bool:
    """若 tool_input 中出现其他用户的 ID，触发 deny"""
    if run_context is None:
        return False
    uid = getattr(run_context, "user_id", None)
    if not uid:
        return False
    # 保守：凡是 input 中出现 "user_id" 字段且不等于当前 run 的 user_id
    for key in ("user_id", "userId", "uid"):
        v = tool_input.get(key)
        if v and str(v) != str(uid):
            return True
    return False


# ---------------------------------------------------------------------------
# 返回 4 条平台规则
# ---------------------------------------------------------------------------

def get_platform_rules() -> list[GuardrailRule]:
    """返回平台内置的 4 条护栏规则（GR-PLATFORM-001 ~ GR-PLATFORM-004）"""
    rules: list[GuardrailRule] = []

    # GR-PLATFORM-001：破坏性命令（bash/shell 专属）
    rules.append(GuardrailRule(
        id="GR-PLATFORM-001",
        tool_pattern=r"bash|Bash|shell|Shell",
        input_patterns=DANGEROUS_PATTERNS,
        reason="平台级护栏：检测到破坏性命令（rm/DROP/FORMAT/fork bomb 等）",
    ))

    # GR-PLATFORM-002：PII 泄露（tool_input 中明文出现密钥）
    rules.append(GuardrailRule(
        id="GR-PLATFORM-002",
        tool_pattern=".*",
        input_patterns=PII_PATTERNS,
        reason="平台级护栏：tool_input 中检测到明文凭据/密钥",
    ))

    # GR-PLATFORM-003：速率限制
    rules.append(GuardrailRule(
        id="GR-PLATFORM-003",
        tool_pattern=".*",
        reason="平台级护栏：工具调用超过速率限制（60s 窗口）",
        custom_match=_rate_limit_check,
    ))

    # GR-PLATFORM-004：跨用户访问
    rules.append(GuardrailRule(
        id="GR-PLATFORM-004",
        tool_pattern=".*",
        reason="平台级护栏：检测到跨用户访问（tool_input 中 user_id 与 run 的 user_id 不符）",
        custom_match=_cross_user_check,
    ))

    return rules
