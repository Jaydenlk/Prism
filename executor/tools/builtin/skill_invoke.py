"""
skill_invoke — Load a skill by name, injecting its full content into context.

DOC-05 Task 5.x: Agent tool to dynamically load a skill during conversation.

The agent prompt tells the AI it can call this tool to get full skill instructions.
Without this tool, skills are only described at Level 1 (name + description);
this tool triggers Level 2 (full SKILL.md body).

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from executor.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from executor.plugins.skill_loader import SkillLoader

logger = structlog.get_logger()


class SkillInvokeTool(BaseTool):
    """Load a skill by name to inject its full instructions into context.

    Triggers Level 2 loading (full SKILL.md body) for the named skill.
    The AI calls this when a task matches a skill's description or triggers.

    capabilities: [] — no special capability required (read-only, no side effects
    beyond injecting context into the current turn)
    """

    capabilities: list[str] = []

    def __init__(self, skill_loader: "SkillLoader") -> None:
        self._skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "skill_invoke"

    @property
    def description(self) -> str:
        return (
            "Load a skill by name to get its full instructions and workflow guidance. "
            "Use when a task matches a skill's description or triggers. "
            "After loading, follow the skill's instructions for the current task."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": (
                        "Name of the skill to invoke "
                        "(e.g., 'brainstorming', 'test-driven-development', "
                        "'superpowers:systematic-debugging')"
                    ),
                }
            },
            "required": ["skill_name"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        """Load skill content and return its full body for context injection."""
        name = (tool_input.get("skill_name") or "").strip()
        if not name:
            return ToolResult(content="Error: skill_name is required", is_error=True)

        content = self._skill_loader.load_skill(name)
        if content is None or not content.is_loaded:
            available = sorted(self._skill_loader.registry.keys())
            available_str = ", ".join(available[:20])
            if len(available) > 20:
                available_str += f" ... ({len(available)} total)"
            return ToolResult(
                content=(
                    f"Skill '{name}' not found. "
                    f"Available skills: {available_str}"
                ),
                is_error=True,
            )

        logger.info("skill_invoke_tool.executed", skill_name=name)
        return ToolResult(content=content.full_text)
