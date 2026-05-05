"""BashTool — execute shell commands with a timeout.

Capability: exec_shell. Captures stdout/stderr (combined output, byte-cap),
returns exit code. Default timeout 60s, max 600s. Default cwd is the executor
process working directory (typically /app inside the container).
"""
from __future__ import annotations

import asyncio
import os

from executor.tools.base import BaseTool, ToolResult

_DEFAULT_TIMEOUT_S = 60
_MAX_TIMEOUT_S = 600
_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KiB combined cap


class BashTool(BaseTool):
    capabilities: list[str] = ["exec_shell"]

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the executor sandbox. Returns combined "
            "stdout+stderr (capped at 64 KiB) and exit code. Default timeout 60s, "
            "max 600s. The shell is /bin/sh -c on Linux containers. Use this for "
            "running scripts, package installs (apt/pip/npm), git operations, etc."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command (single-line or multi-line script).",
                },
                "timeout_s": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_TIMEOUT_S,
                    "description": f"Timeout in seconds (default {_DEFAULT_TIMEOUT_S}).",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: process cwd).",
                },
            },
            "required": ["command"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        command = tool_input.get("command")
        if not command:
            return ToolResult(content="command is required", is_error=True)
        timeout = min(_MAX_TIMEOUT_S, max(1, int(tool_input.get("timeout_s", _DEFAULT_TIMEOUT_S))))
        cwd = tool_input.get("cwd") or os.getcwd()
        if not os.path.isdir(cwd):
            return ToolResult(content=f"cwd does not exist: {cwd}", is_error=True)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            return ToolResult(content=f"Spawn failed: {type(e).__name__}: {e}", is_error=True)

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(content=f"Command timed out after {timeout}s", is_error=True)

        out = stdout.decode("utf-8", errors="replace")
        if len(stdout) > _MAX_OUTPUT_BYTES:
            cut_at = _MAX_OUTPUT_BYTES
            out = stdout[:cut_at].decode("utf-8", errors="replace") + (
                f"\n\n... (output truncated at {_MAX_OUTPUT_BYTES} bytes; "
                f"original size {len(stdout)})"
            )

        exit_code = proc.returncode
        header = f"$ {command.splitlines()[0]}\n[exit {exit_code}]\n" if exit_code != 0 else ""
        return ToolResult(content=f"{header}{out}".rstrip() or "(no output)", is_error=(exit_code != 0))
