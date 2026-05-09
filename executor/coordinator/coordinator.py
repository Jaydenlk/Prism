"""
Coordinator — 多步骤任务编排器(v4:Plan checkpoint 持久化 + 崩溃恢复)

工作流:
1. 接收用户任务
2. Fork Planner Agent 生成执行计划
3. 解析计划为 Plan 对象
4. 按步骤顺序 Fork Worker Agents 执行
5. 每个 step 完成后,将结果累积到上下文
6. 可选:Fork Verifier Agent 验证最终结果
7. 调用 Synthesizer 合成最终输出

简单任务判定:如果 Planner 返回的计划只有 1 个步骤,
跳过 Coordinator 模式,直接由 General Agent 执行。

v4 核心修订(ADR-040, PRD 原标 ADR-036):
- 每个 step 的开始/完成通过 callback.coordinator_plan_update 写 coordinator_plans 表
- resume_from_checkpoint() 类方法:读 coordinator_plans 表从 current_step 恢复
- execute(existing_plan, resume_from_step) 两参数支持恢复

进程边界:本模块只 import executor.*,禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from executor.coordinator.fork_briefing import ForkBriefing
from executor.coordinator.plan import Plan, PlanStep, deserialize_plan, serialize_plan

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback
    from executor.coordinator.fork_manager import ForkManager
    from executor.engine.synthesizer import Synthesizer

logger = structlog.get_logger()


class Coordinator:
    """v4:每 step checkpoint 到 coordinator_plans 表"""

    def __init__(
        self,
        fork_manager: "ForkManager",
        callback: "BackendCallback",
        synthesizer: "Synthesizer",
        plan_id: str,                          # v4:Plan 持久化 ID
        resume_from_step: int | None = None,   # v4:恢复执行起点
    ):
        self._fork = fork_manager
        self._callback = callback
        self._synthesizer = synthesizer
        self._plan_id = plan_id
        self._resume_from_step = resume_from_step

    async def execute(self, user_prompt: str, existing_plan: Plan | None = None) -> str:
        """
        执行完整的 Coordinator 工作流(v4:带 checkpoint)。

        existing_plan: 恢复执行时传入,跳过 _plan 步骤
        """
        # Step 1: 规划(或复用 checkpoint 中的 Plan)
        plan = existing_plan or await self._plan(user_prompt)

        # 简单任务判定
        if len(plan.steps) <= 1:
            result = await self._fork.fork(
                agent_type="general",
                briefing=ForkBriefing(goal=user_prompt, why="single-step task"),
            )
            return result.synthesis

        # v4:初始 checkpoint
        start_idx = self._resume_from_step or 0
        await self._callback.coordinator_plan_update(
            plan_id=self._plan_id,
            plan_json=serialize_plan(plan),
            current_step=start_idx,
            total_steps=len(plan.steps),
            status="running",
            step_results=[s.result for s in plan.steps if s.result is not None],
        )

        # Step 2: 按顺序执行(从 resume_from_step 开始)
        step_results: list[str] = [s.result for s in plan.steps[:start_idx] if s.result is not None]

        for i, step in enumerate(plan.steps[start_idx:], start=start_idx):
            # v4:step 开始 checkpoint
            await self._callback.coordinator_plan_update(
                plan_id=self._plan_id,
                current_step=i,
                total_steps=len(plan.steps),
                status="running",
                step_results=step_results,
            )
            await self._callback.harness_event("step_start", {"step_id": step.step_id})

            # 将已完成步骤的结果注入到当前步骤的上下文中
            context_prefix = self._build_step_context(plan, step_results, step)
            briefing = ForkBriefing(
                goal=step.task_prompt,
                why=step.description,
                context=context_prefix,
            )

            result = await self._fork.fork(
                agent_type=step.agent_type,
                briefing=briefing,
            )

            step.status = "completed" if result.success else "failed"
            step.result = result.synthesis if result.success else f"[步骤失败: {result.error}]"
            step_results.append(step.result)

            await self._callback.harness_event("step_end", {
                "step_id": step.step_id,
                "status": step.status,
            })

        # v4:完成 checkpoint
        await self._callback.coordinator_plan_update(
            plan_id=self._plan_id,
            current_step=len(plan.steps),
            total_steps=len(plan.steps),
            status="completed",
            step_results=step_results,
        )

        # Step 3: 合成
        final = self._synthesizer.synthesize(
            task_summary=plan.task_summary,
            step_results=[(s.description, s.result) for s in plan.steps],
        )

        return final

    @classmethod
    async def resume_from_checkpoint(
        cls,
        plan_id: str,
        db_session,
        fork_manager: "ForkManager",
        callback: "BackendCallback",
        synthesizer: "Synthesizer",
    ) -> tuple["Coordinator", Plan]:
        """
        v4:从 coordinator_plans 表恢复执行状态(DOC-07 v4 Task 7.4 调用)

        返回 (Coordinator 实例, 反序列化的 Plan)。
        调用方在 recover 后应执行 coordinator.execute(user_prompt, existing_plan=plan)。
        """
        row = db_session.execute(
            "SELECT plan_json, current_step_index FROM coordinator_plans WHERE id = :pid",
            {"pid": plan_id},
        ).first()
        if not row:
            raise ValueError(f"No checkpoint for plan {plan_id}")

        plan_json = row.plan_json if isinstance(row.plan_json, dict) else row[0]
        current_step = row.current_step_index if hasattr(row, "current_step_index") else row[1]
        plan = deserialize_plan(plan_json)
        coordinator = cls(
            fork_manager=fork_manager,
            callback=callback,
            synthesizer=synthesizer,
            plan_id=plan_id,
            resume_from_step=current_step,
        )
        return coordinator, plan

    async def _plan(self, user_prompt: str) -> Plan:
        """Fork Planner Agent 生成计划(v4 briefing)"""
        result = await self._fork.fork(
            agent_type="planner",
            briefing=ForkBriefing(
                goal=user_prompt,
                why="Coordinator 需要一个可执行的 step 计划",
                expected_output="结构化 JSON 计划,含 Critical Files for Implementation",
            ),
        )

        if not result.success:
            # 规划失败,回退到单步 general
            return Plan(
                task_summary=user_prompt,
                steps=[
                    PlanStep(
                        step_id=1,
                        description=user_prompt,
                        agent_type="general",
                        task_prompt=user_prompt,
                    )
                ],
            )

        plan = Plan.parse_from_text(result.synthesis)

        # 通知前端计划
        for step in plan.steps:
            await self._callback.harness_event("plan_step", {
                "step_id": step.step_id,
                "type": step.agent_type,
                "description": step.description,
            })

        return plan

    def _build_step_context(
        self,
        plan: Plan,
        results_so_far: list[str],
        current_step: PlanStep,
    ) -> str:
        """为当前步骤构建上下文前缀,包含已完成步骤的结果"""
        if not results_so_far:
            return f"总体任务:{plan.task_summary}"

        parts = [f"总体任务:{plan.task_summary}", "", "已完成的步骤:"]
        for step, result in zip(plan.steps[: len(results_so_far)], results_so_far):
            parts.append(f"步骤 {step.step_id} ({step.description}): {result[:500]}")

        return "\n".join(parts)
