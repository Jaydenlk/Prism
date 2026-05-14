from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PromptSegment:
    header: str
    content: str


class PromptAssembler:
    def __init__(self) -> None:
        self._segments: list[PromptSegment] = []

    def add_base(self, agent_type: str) -> None:
        role_map = {
            "chat": "You are a helpful AI assistant.",
            "explore": "You are a code exploration assistant. Read and analyze code, but do not modify it.",
            "build": "You are a software engineering assistant. Write clean, tested code.",
            "coordinator": "You coordinate multi-step tasks by breaking them into subtasks.",
            "plugin_builder": (
                "You are a Plugin Builder agent. Your job is to research existing solutions "
                "and create plugin manifests for the Prism platform.\n\n"
                "WORKFLOW:\n"
                "1. Search for existing open-source solutions (GitHub, npm, PyPI)\n"
                "2. Evaluate what exists and what needs to be built\n"
                "3. Create the plugin files in the workspace\n\n"
                "CRITICAL OUTPUT REQUIREMENT:\n"
                "You MUST end your response with a fenced YAML manifest block:\n"
                "```yaml\n"
                "name: my-plugin-name\n"
                "description: One line description\n"
                "version: \"1.0.0\"\n"
                "type: tool\n"
                "allowed_tools:\n"
                "  - Bash\n"
                "  - WebSearch\n"
                "```\n"
                "DO NOT end with just a research report or question. Always conclude with the YAML block."
            ),
        }
        text = role_map.get(agent_type, role_map["chat"])
        self._segments.append(PromptSegment(header="Role", content=text))

    def add_workspace(self, workspace_path: str) -> None:
        if not workspace_path or workspace_path == "/tmp":
            return
        try:
            items = sorted(os.listdir(workspace_path))[:20]
        except OSError:
            return
        if not items:
            return
        listing = "\n".join(f"- {item}" for item in items)
        self._segments.append(PromptSegment(
            header="Workspace",
            content=f"Current directory: `{workspace_path}`\n{listing}",
        ))

    def add_memories(self, memories: list[dict]) -> None:
        if not memories:
            return
        lines = []
        for m in memories:
            text = m.get("memory", m.get("text", ""))
            if text:
                lines.append(f"- {text}")
        if lines:
            self._segments.append(PromptSegment(
                header="About the User",
                content="You already know:\n" + "\n".join(lines),
            ))

    def add_skill(self, skill_prompt: str) -> None:
        if skill_prompt:
            self._segments.append(PromptSegment(header="Task Guidelines", content=skill_prompt))

    def add_constraints(self, constraints: str) -> None:
        if constraints:
            self._segments.append(PromptSegment(header="Constraints", content=constraints))

    def assemble(self) -> str:
        if not self._segments:
            return ""
        parts = []
        for seg in self._segments:
            parts.append(f"## {seg.header}\n{seg.content}")
        return "\n\n".join(parts)
