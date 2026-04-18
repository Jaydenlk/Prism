"""
工具基类 — 声明式 Schema 定义

每个工具声明：
- name: 工具名称（全局唯一，格式 "{namespace}__{tool_name}" 或 "{tool_name}"）
- description: 给模型看的描述
- input_schema: JSON Schema（模型生成的参数必须符合此 Schema）
- execute(): 实际执行逻辑

进程边界：本模块只 import executor.adapters.base，禁止 import backend.app.*
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果"""

    content: str  # 输出内容（纯文本或 JSON 字符串）
    is_error: bool = False


class BaseTool(ABC):
    """工具抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（全局唯一，格式 '{namespace}__{tool_name}' 或 '{tool_name}'）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """给模型看的描述"""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema（模型生成的参数必须符合此 Schema）"""
        ...

    @abstractmethod
    async def execute(self, tool_input: dict) -> ToolResult:
        """执行工具。子类实现具体逻辑。"""
        ...

    def to_definition(self) -> "ToolDefinition":
        """转为传给模型的 ToolDefinition"""
        from executor.adapters.base import ToolDefinition

        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )
