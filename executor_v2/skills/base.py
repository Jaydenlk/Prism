from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    description: str
    system_prompt_addition: str
    tools: list[str] = field(default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"])
    verify: bool = False
