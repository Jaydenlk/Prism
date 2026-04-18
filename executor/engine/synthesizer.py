"""
Synthesizer — 多步骤结果合成

将 Coordinator 执行的多个步骤的结果合成为一个连贯的最终输出。
Phase 1 使用模板化合成(不调用模型),Phase 2 可升级为 LLM 合成。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations


class Synthesizer:
    """多步骤结果合成器(Phase 1 模板化)"""

    def synthesize(self, task_summary: str, step_results: list[tuple[str, str]]) -> str:
        """
        合成最终输出。

        step_results: [(description, result), ...]
        """
        parts = [f"## 任务完成\n\n**目标**:{task_summary}\n"]

        for desc, result in step_results:
            parts.append(f"### {desc}\n{result}\n")

        return "\n".join(parts)
