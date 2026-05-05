"""GlobTool — find files by glob pattern.

Capability: read_file. Wraps Python's pathlib.Path.glob. Returns paths sorted
by modification time (newest first), capped at 1000 results.
"""
from __future__ import annotations

from pathlib import Path

from executor.tools.base import BaseTool, ToolResult

_MAX_RESULTS = 1000


class GlobTool(BaseTool):
    capabilities: list[str] = ["read_file"]

    @property
    def name(self) -> str:
        return "Glob"

    @property
    def description(self) -> str:
        return (
            "Find files matching a glob pattern, sorted by modification time (newest "
            "first). Patterns: `*.py` (single dir), `**/*.py` (recursive). The base "
            "directory defaults to cwd; pass `path` to scope to a subdirectory. "
            "Returns up to 1000 paths."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. `**/*.ts`, `src/*.py`).",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory (default: current working dir).",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        pattern = tool_input.get("pattern")
        if not pattern:
            return ToolResult(content="pattern is required", is_error=True)
        base = Path(tool_input.get("path") or ".")
        if not base.is_dir():
            return ToolResult(content=f"path is not a directory: {base}", is_error=True)

        try:
            matches = [p for p in base.glob(pattern) if p.is_file()]
        except OSError as e:
            return ToolResult(content=f"Glob failed: {type(e).__name__}: {e}", is_error=True)

        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        truncated = len(matches) > _MAX_RESULTS
        matches = matches[:_MAX_RESULTS]

        if not matches:
            return ToolResult(content=f"No files match `{pattern}` under {base}.")

        body = "\n".join(str(p) for p in matches)
        if truncated:
            body += f"\n\n... ({_MAX_RESULTS} of >{_MAX_RESULTS} results shown; refine pattern.)"
        return ToolResult(content=body)
