"""ReadTool — read file contents from the executor sandbox filesystem.

Capability: read_file. Operates on absolute or working-dir-relative paths.
Returns content with line-number prefix (cat -n style) so agents can pinpoint
edits accurately. Supports offset/limit for large files.
"""
from __future__ import annotations

import os

from executor.tools.base import BaseTool, ToolResult

_DEFAULT_LIMIT = 2000  # lines
_MAX_LIMIT = 10000


class ReadTool(BaseTool):
    capabilities: list[str] = ["read_file"]

    @property
    def name(self) -> str:
        return "Read"

    @property
    def description(self) -> str:
        return (
            "Read a file from the executor filesystem. Returns content prefixed with "
            "1-indexed line numbers (e.g. `   42\\tcontent`). Use `offset` + `limit` "
            "for files > 2000 lines. Path must be absolute or relative to the executor "
            "working directory. Errors when the path does not exist, is a directory, "
            "or is not UTF-8 decodable."
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
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-indexed first line to read (default: 1).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_LIMIT,
                    "description": f"Max lines to return (default: {_DEFAULT_LIMIT}).",
                },
            },
            "required": ["path"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        path = tool_input.get("path")
        if not path:
            return ToolResult(content="path is required", is_error=True)
        if not os.path.exists(path):
            return ToolResult(content=f"File not found: {path}", is_error=True)
        if os.path.isdir(path):
            return ToolResult(content=f"Path is a directory, not a file: {path}", is_error=True)

        offset = max(1, int(tool_input.get("offset", 1)))
        limit = min(_MAX_LIMIT, max(1, int(tool_input.get("limit", _DEFAULT_LIMIT))))

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            return ToolResult(content=f"Read failed: {type(e).__name__}: {e}", is_error=True)

        end = offset + limit
        slice_ = lines[offset - 1 : end - 1]
        out = "".join(f"{offset + i:6d}\t{line}" for i, line in enumerate(slice_))
        if not out:
            return ToolResult(content=f"(empty range; file has {len(lines)} lines)")
        return ToolResult(content=out)
