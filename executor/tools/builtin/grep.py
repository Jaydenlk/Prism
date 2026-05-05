"""GrepTool — regex content search across files.

Capability: read_file. Uses ripgrep (rg) when available (fast, .gitignore-aware),
falls back to a Python glob+regex scanner. Returns matches with file:line:text.
"""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from executor.tools.base import BaseTool, ToolResult

_MAX_MATCHES = 500
_MAX_OUTPUT_BYTES = 64 * 1024


class GrepTool(BaseTool):
    capabilities: list[str] = ["read_file"]

    @property
    def name(self) -> str:
        return "Grep"

    @property
    def description(self) -> str:
        return (
            "Search file contents with a regex pattern. Returns up to 500 matches as "
            "`file:line:matched-text`. Uses ripgrep when installed (.gitignore-aware), "
            "falls back to Python scan otherwise. Filter by glob (e.g. `*.py`) or path "
            "to limit scope."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex (Python syntax)."},
                "path": {"type": "string", "description": "Base dir (default: cwd)."},
                "glob": {
                    "type": "string",
                    "description": "File pattern filter (e.g. `*.py`, `**/*.{ts,tsx}`).",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Match case-insensitively (default: false).",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        pattern = tool_input.get("pattern")
        if not pattern:
            return ToolResult(content="pattern is required", is_error=True)
        base = tool_input.get("path") or "."
        glob_filter = tool_input.get("glob")
        case_insensitive = bool(tool_input.get("case_insensitive", False))

        if shutil.which("rg"):
            return await self._rg(pattern, base, glob_filter, case_insensitive)
        return self._python_scan(pattern, base, glob_filter, case_insensitive)

    async def _rg(self, pattern: str, base: str, glob_filter: str | None, ci: bool) -> ToolResult:
        cmd = ["rg", "--line-number", "--no-heading", "--max-count", str(_MAX_MATCHES)]
        if ci:
            cmd.append("--ignore-case")
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.extend([pattern, base])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except (OSError, asyncio.TimeoutError) as e:
            return ToolResult(content=f"rg failed: {type(e).__name__}: {e}", is_error=True)

        out = stdout.decode("utf-8", errors="replace")
        if proc.returncode == 1 and not out:
            return ToolResult(content=f"No matches for /{pattern}/ in {base}.")
        if proc.returncode not in (0, 1):
            err = stderr.decode("utf-8", errors="replace").strip()
            return ToolResult(content=f"rg exit {proc.returncode}: {err}", is_error=True)
        return ToolResult(content=out[:_MAX_OUTPUT_BYTES])

    def _python_scan(self, pattern: str, base: str, glob_filter: str | None, ci: bool) -> ToolResult:
        try:
            regex = re.compile(pattern, re.IGNORECASE if ci else 0)
        except re.error as e:
            return ToolResult(content=f"Invalid regex: {e}", is_error=True)

        base_path = Path(base)
        if not base_path.is_dir():
            return ToolResult(content=f"path is not a directory: {base}", is_error=True)
        files = base_path.glob(glob_filter) if glob_filter else base_path.rglob("*")

        matches: list[str] = []
        for path in files:
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, start=1):
                        if regex.search(line):
                            matches.append(f"{path}:{lineno}:{line.rstrip()}")
                            if len(matches) >= _MAX_MATCHES:
                                break
            except OSError:
                continue
            if len(matches) >= _MAX_MATCHES:
                break

        if not matches:
            return ToolResult(content=f"No matches for /{pattern}/ in {base}.")
        return ToolResult(content="\n".join(matches)[:_MAX_OUTPUT_BYTES])
