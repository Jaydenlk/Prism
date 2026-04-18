"""
EchoTool — 最小测试工具（echo 输入内容）

用于开发/测试阶段验证 TAOR 循环工具执行路径。
生产环境不暴露给终端用户（通过权限系统控制）。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.tools.base import BaseTool, ToolResult


class EchoTool(BaseTool):
    """Echo 工具：原样返回 message 字段，前缀 'Echo: '"""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "回显输入内容，用于测试工具调用路径。输入 message 字段，返回 'Echo: {message}'。"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要回显的消息内容",
                }
            },
            "required": ["message"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        message = tool_input["message"]
        return ToolResult(content=f"Echo: {message}")
