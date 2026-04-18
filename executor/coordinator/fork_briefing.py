"""
ForkBriefing — 结构化 Fork 任务入参(v4 ADR-035)

替代 v3.1 的自由格式 task 字符串。6 字段强制结构化,
让子 Agent 更容易定位目标,也让 Fork 调用处的代码更可审查。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ForkBriefing:
    goal: str                                              # 目标(一句话)
    why: str                                               # 动机,帮助子 Agent 决策
    excluded: list[str] = field(default_factory=list)      # 明确排除的做法
    context: str = ""                                      # 已知背景,避免重复调研
    expected_output: str = ""                              # 期望的 synthesis 格式
    file_references: list[str] = field(default_factory=list)  # 需要关注的文件路径

    def to_prompt(self) -> str:
        """渲染为子 Agent 的初始 user prompt（markdown 结构化）"""
        lines = [f"## 目标\n{self.goal}", f"\n## 动机\n{self.why}"]
        if self.excluded:
            lines.append("\n## 必须排除的做法\n- " + "\n- ".join(self.excluded))
        if self.context:
            lines.append(f"\n## 已知背景\n{self.context}")
        if self.file_references:
            lines.append("\n## 关注文件\n- " + "\n- ".join(self.file_references))
        if self.expected_output:
            lines.append(f"\n## 期望输出\n{self.expected_output}")
        return "\n".join(lines)


# v4 ADR-034:Fork 3 条硬约束(注入到子 Agent system prompt)
FORK_HARD_CONSTRAINTS = """
**Fork Agent 硬约束(不可违反)**:
1. 禁止覆盖父 Agent 的 model / provider。这是 Prompt Cache 共享的基础,覆盖会导致 cache miss。
2. 禁止偷窥其他并行 Fork 的 outputFile(即使文件可读)。跨 Fork 信息泄露破坏隔离。
3. 禁止预言未执行的结果。synthesis 必须基于本 Fork 实际执行的工具调用结果,
   不能"我猜应该是 X"。如果工具未执行或失败,明确在 synthesis 中说明。
"""
