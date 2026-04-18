"""
Plan 数据结构 — Planner Agent 的输出格式

Coordinator 解析 Planner 的结构化输出为 Plan 对象，然后按步骤执行。

两级解析策略（ADR-040 前置）:
1. 结构化 JSON(Planner 遵循 output_format 时) - 优先
2. Markdown 列表(正则回退) - 失败则单步兜底

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

VALID_AGENT_TYPES = {"general", "research", "explore", "planner", "verifier", "coordinator", "plugin_builder"}


@dataclass
class PlanStep:
    """单个执行步骤"""

    step_id: int
    description: str
    agent_type: str                                         # "research" | "general" | "verifier" | ...
    task_prompt: str                                        # 交给子 Agent 的具体指令
    depends_on: list[int] = field(default_factory=list)     # 依赖的 step_id 列表
    status: str = "pending"                                 # pending | running | completed | failed | skipped
    result: str = ""                                        # 执行结果


@dataclass
class Plan:
    """执行计划"""

    task_summary: str                                       # 任务理解
    steps: list[PlanStep] = field(default_factory=list)

    @classmethod
    def parse_from_text(cls, planner_output: str) -> "Plan":
        """
        从 Planner Agent 的文本输出解析为 Plan 对象。

        支持两种格式:
        1. 结构化 JSON(Planner 遵循 output_format 时)
        2. Markdown 列表(回退解析)

        解析失败时返回单步 Plan(整个任务作为一个 general step)。
        """
        text = (planner_output or "").strip()
        if not text:
            return cls._single_step_fallback("(空规划)", "")

        parsed = cls._try_parse_json(text)
        if parsed is not None:
            return parsed

        parsed = cls._try_parse_markdown(text)
        if parsed is not None:
            return parsed

        return cls._single_step_fallback(text[:500], text)

    @classmethod
    def _try_parse_json(cls, text: str) -> "Plan | None":
        """尝试解析 JSON(包括 ```json ... ``` 围栏代码块)"""
        fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        candidates: list[str] = []
        if fenced:
            candidates.append(fenced.group(1).strip())
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            candidates.append(brace.group(0))
        candidates.append(text)

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            raw_steps = payload.get("steps")
            if not isinstance(raw_steps, list) or not raw_steps:
                continue
            steps: list[PlanStep] = []
            for i, raw in enumerate(raw_steps, start=1):
                if not isinstance(raw, dict):
                    continue
                step = PlanStep(
                    step_id=int(raw.get("step_id", i)),
                    description=str(raw.get("description", "")).strip() or f"步骤 {i}",
                    agent_type=cls._normalize_agent_type(raw.get("agent_type")),
                    task_prompt=str(raw.get("task_prompt", raw.get("description", ""))).strip(),
                    depends_on=[int(x) for x in raw.get("depends_on", []) if isinstance(x, (int, str))
                                and str(x).lstrip("-").isdigit()],
                )
                steps.append(step)
            if not steps:
                continue
            summary = str(payload.get("task_summary") or payload.get("summary") or "").strip()
            if not summary:
                summary = steps[0].description
            return cls(task_summary=summary, steps=steps)
        return None

    @classmethod
    def _try_parse_markdown(cls, text: str) -> "Plan | None":
        """解析 markdown 列表(形如 `1. [research] 搜索竞品` 或 `- [general] 整理`)"""
        step_line_re = re.compile(
            r"^\s*(?:\d+\.|[-*])\s*\[(?P<agent>[a-zA-Z_]+)\]\s*(?P<desc>.+?)\s*$",
            re.MULTILINE,
        )
        matches = list(step_line_re.finditer(text))
        if not matches:
            return None

        # task_summary: 取第一行非 step 的非空行(若有)
        summary = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if step_line_re.match(line):
                break
            # 跳过标题符号
            summary = stripped.lstrip("# ").strip()
            if summary:
                break
        if not summary:
            summary = matches[0].group("desc").strip()

        steps: list[PlanStep] = []
        for i, m in enumerate(matches, start=1):
            desc = m.group("desc").strip()
            agent_type = cls._normalize_agent_type(m.group("agent"))
            steps.append(
                PlanStep(
                    step_id=i,
                    description=desc,
                    agent_type=agent_type,
                    task_prompt=desc,
                )
            )
        return cls(task_summary=summary, steps=steps)

    @classmethod
    def _single_step_fallback(cls, summary: str, user_prompt: str) -> "Plan":
        """解析失败兜底:整个任务作为一个 general step"""
        return cls(
            task_summary=summary or "(解析失败)",
            steps=[
                PlanStep(
                    step_id=1,
                    description=summary or "整体任务",
                    agent_type="general",
                    task_prompt=user_prompt or summary,
                )
            ],
        )

    @staticmethod
    def _normalize_agent_type(raw: object) -> str:
        """规范化 agent_type: research→explore 别名兼容; 非法值回落 general"""
        value = str(raw or "").strip().lower()
        if value in ("research", "explore"):
            return "explore"
        if value in VALID_AGENT_TYPES:
            return value
        return "general"


def serialize_plan(plan: Plan) -> dict:
    """将 Plan 序列化为可持久化 dict(写入 coordinator_plans.plan_json 字段)"""
    return asdict(plan)


def deserialize_plan(payload: dict) -> Plan:
    """从持久化 dict 反序列化 Plan(resume 时用)"""
    steps = [PlanStep(**raw) for raw in payload.get("steps", [])]
    return Plan(task_summary=payload.get("task_summary", ""), steps=steps)
