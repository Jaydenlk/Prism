"""EditTool — surgical find-replace on a file.

Capability: write_file. Performs exact-string replacement. Fails if the
old_string is not found or matches multiple times (unless replace_all=True).
"""
from __future__ import annotations

import os

from executor.tools.base import BaseTool, ToolResult


class EditTool(BaseTool):
    capabilities: list[str] = ["write_file"]

    @property
    def name(self) -> str:
        return "Edit"

    @property
    def description(self) -> str:
        return (
            "Replace one or more occurrences of an exact string in a file. By default "
            "fails if old_string is not found or matches >1 time (forces caller to "
            "supply enough context to be unambiguous). Set replace_all=true to replace "
            "every occurrence (useful for renames). Preserves indentation/whitespace exactly."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path."},
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find. Must be unique unless replace_all=true.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement (must differ from old_string).",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false).",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        path = tool_input.get("path")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        replace_all = bool(tool_input.get("replace_all", False))

        if not path:
            return ToolResult(content="path is required", is_error=True)
        if old == new:
            return ToolResult(content="new_string must differ from old_string", is_error=True)
        if not os.path.exists(path):
            return ToolResult(content=f"File not found: {path}", is_error=True)

        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
        except OSError as e:
            return ToolResult(content=f"Read failed: {type(e).__name__}: {e}", is_error=True)

        count = original.count(old)
        if count == 0:
            return ToolResult(content=f"old_string not found in {path}", is_error=True)
        if count > 1 and not replace_all:
            return ToolResult(
                content=(
                    f"old_string matches {count} times in {path}; provide more context "
                    "to make it unique, or set replace_all=true."
                ),
                is_error=True,
            )

        updated = original.replace(old, new) if replace_all else original.replace(old, new, 1)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
        except OSError as e:
            return ToolResult(content=f"Write failed: {type(e).__name__}: {e}", is_error=True)

        replaced = count if replace_all else 1
        return ToolResult(content=f"Replaced {replaced} occurrence(s) in {os.path.abspath(path)}")
