"""WriteTool — write/overwrite a file on the executor sandbox filesystem.

Capability: write_file. Creates parent directories as needed. Returns the
absolute path written and the byte size.
"""
from __future__ import annotations

import os

from executor.tools.base import BaseTool, ToolResult


class WriteTool(BaseTool):
    capabilities: list[str] = ["write_file"]

    @property
    def name(self) -> str:
        return "Write"

    @property
    def description(self) -> str:
        return (
            "Write content to a file (overwrite if exists). Creates parent directories "
            "as needed. UTF-8 encoded. Use Edit instead for surgical changes to existing "
            "files. Returns the absolute path and byte count on success."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path (absolute, or relative to cwd).",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content (UTF-8). Newlines preserved literally.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        path = tool_input.get("path")
        content = tool_input.get("content")
        if not path:
            return ToolResult(content="path is required", is_error=True)
        if content is None:
            return ToolResult(content="content is required (use empty string to truncate)", is_error=True)

        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return ToolResult(content=f"Write failed: {type(e).__name__}: {e}", is_error=True)

        size = len(content.encode("utf-8"))
        return ToolResult(content=f"Wrote {size} bytes to {os.path.abspath(path)}")
