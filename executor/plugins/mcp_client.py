"""
MCP stdio 客户端

通过 stdio 子进程与 MCP Server 通信：
1. 启动 Server: asyncio.create_subprocess_exec(command, args, env, stdin=PIPE, stdout=PIPE)
2. 初始化: 发送 initialize request，获取 server capabilities
3. 工具发现: 发送 tools/list request，获取工具列表
4. 工具调用: 发送 tools/call request，获取结果
5. 关闭: 发送 shutdown，terminate 子进程

MCP 协议使用 JSON-RPC 2.0 over stdio（每行一个 JSON）。

异步修复 (P0, Part A): asyncio.create_subprocess_exec() + process.stdout.readline() 非阻塞读取，
避免阻塞事件循环（对比 subprocess.Popen 的阻塞 readline）。

进程边界：本模块只 import 标准库 + executor.tools.*，禁止 import backend.app.*

ADR-046: MCP instructions 双通道注入（Registry instructions → PromptAssembler <mcp_instructions>，
         Tool instructions → tool_grammar_section）
ADR-047: agent-scoped MCP 白名单（AgentDefinition.mcp_servers 过滤，filter_mcp_tools() 生效）
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING

import structlog

from executor.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# scope 二值常量（与 McpServer.scope 对齐，DOC-01 v4 §4.2）
# ---------------------------------------------------------------------------

SCOPE_SYSTEM = "system"
SCOPE_USER = "user"


# ---------------------------------------------------------------------------
# MCPClient — stdio 双通道客户端
# ---------------------------------------------------------------------------


class MCPClient:
    """MCP Server stdio 客户端（异步，ADR-046）

    职责：
    - 启动 MCP Server 子进程（asyncio.create_subprocess_exec，P0 异步修复）
    - 执行 JSON-RPC 2.0 over stdio 握手（initialize → notifications/initialized）
    - 发现工具列表（tools/list）
    - 获取 Registry instructions（server.info.instructions → ADR-046 双通道）
    - 执行工具调用（tools/call）
    - 优雅关闭子进程（shutdown + exit + terminate）

    scope 二值：
    - "system": 平台级 MCP Server，所有用户可见（需 AgentDefinition.mcp_servers 白名单确认）
    - "user":   用户个人安装，仅对该用户可见
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str],
        env: dict[str, str],
        scope: str = SCOPE_USER,
    ) -> None:
        """初始化 MCP Client。

        Args:
            server_name: MCP Server 的唯一名称（用于工具名称命名空间 mcp__{name}__{tool}）
            command:     可执行文件路径（如 "npx", "python", "uvx"）
            args:        命令行参数列表
            env:         注入子进程的额外环境变量（与 os.environ 合并）
            scope:       "system" | "user"（对齐 McpServer.scope，ADR-047）
        """
        self._server_name = server_name
        self._command = command
        self._args = args
        self._env = env
        self._scope = scope
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._tools: list[dict] = []
        self._instructions: str = ""

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动 MCP Server 子进程并完成初始化握手。

        步骤：
        1. asyncio.create_subprocess_exec → 异步子进程（P0: 非阻塞 I/O）
        2. initialize request → 获取 server capabilities + instructions
        3. notifications/initialized 通知
        4. tools/list → 填充 self._tools

        Raises:
            RuntimeError: 子进程启动失败或 MCP 握手失败
        """
        full_env = {**dict(os.environ), **self._env}

        # P0 异步修复：使用 asyncio.create_subprocess_exec 避免阻塞事件循环
        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )

        logger.info(
            "mcp.client.started",
            server_name=self._server_name,
            scope=self._scope,
            pid=self._process.pid,
        )

        # 初始化握手（JSON-RPC initialize）
        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "prism", "version": "2.0"},
            },
        )

        # 发送 initialized 通知（服务端等待此通知才开始工作）
        await self._send_notification("notifications/initialized", {})

        # ADR-046 双通道第一路：Registry instructions（全局说明）
        self._instructions = init_result.get("instructions", "")

        # 工具发现
        tools_result = await self._send_request("tools/list", {})
        self._tools = tools_result.get("tools", [])

        logger.info(
            "mcp.client.initialized",
            server_name=self._server_name,
            tool_count=len(self._tools),
            has_instructions=bool(self._instructions),
        )

    async def stop(self) -> None:
        """优雅关闭 MCP Server 子进程。

        依次：shutdown request → exit notification → terminate（fallback）
        """
        if self._process is None:
            return
        try:
            await self._send_request("shutdown", {})
            await self._send_notification("exit", {})
        except Exception as exc:
            logger.warning(
                "mcp.client.shutdown_error",
                server_name=self._server_name,
                error=str(exc),
            )
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except Exception:
            pass
        self._process = None
        logger.info("mcp.client.stopped", server_name=self._server_name)

    # ------------------------------------------------------------------
    # 工具访问
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[dict]:
        """返回 MCP Server 提供的工具列表（原始 MCP 格式）。

        每项为 {"name": ..., "description": ..., "inputSchema": {...}} 字典。
        调用方用此列表构建 MCPToolWrapper 并注册到 ToolRegistry。
        """
        return list(self._tools)

    def get_instructions(self) -> str:
        """返回 MCP Server 的 Registry instructions（ADR-046 第一通道）。

        注入到 PromptAssembler 动态 section 的 <mcp_instructions>，
        解释"这个 Server 是干什么的 + 使用约定"。
        返回空字符串表示该 Server 未提供全局说明。
        """
        return self._instructions

    @property
    def server_name(self) -> str:
        """Server 唯一名称（用于工具命名空间）。"""
        return self._server_name

    @property
    def scope(self) -> str:
        """scope 二值："system" | "user"（ADR-047）。"""
        return self._scope

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具，返回合并的文本结果。

        ADR-046 第二通道：Tool instructions 通过每个 tool 的 description 在
        tool_grammar_section 展现，此方法只负责执行并返回文本内容。

        Args:
            tool_name:  MCP Server 内部工具名（不含命名空间前缀）
            arguments:  工具参数 dict

        Returns:
            合并所有 content[type=text].text 的字符串

        Raises:
            RuntimeError: MCP 协议错误或子进程已关闭
        """
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        contents = result.get("content", [])
        texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
        return "\n".join(texts)

    # ------------------------------------------------------------------
    # agent-scoped MCP 白名单过滤（ADR-047）
    # ------------------------------------------------------------------

    def list_mcp_tool_pairs(self) -> list[tuple[str, str]]:
        """返回 (server_name, mcp_tool_name) 元组列表。

        供 AgentDefinition.filter_mcp_tools() 按 mcp_servers 白名单过滤。
        过滤后的 tool_name 才注册到子 Agent 的 ToolRegistry，
        实现 ADR-047: agent-scoped MCP 白名单。

        示例：
            [("github", "create_issue"), ("slack", "send_message")]
        """
        return [(self._server_name, t["name"]) for t in self._tools]

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 over stdio（内部方法）
    # ------------------------------------------------------------------

    async def _send_request(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC request，异步等待 response（P0 非阻塞）。

        使用 asyncio.subprocess.Process 的异步 stdout.readline()，
        不阻塞事件循环（对比 subprocess.Popen 的同步 readline）。

        Raises:
            RuntimeError: 子进程未启动、无响应、或 MCP 返回 error
        """
        if self._process is None:
            raise RuntimeError(
                f"MCPClient({self._server_name}) 未启动，请先调用 start()"
            )
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(request) + "\n"

        # 异步写入 stdin
        assert self._process.stdin is not None
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        # 异步读取 stdout（P0 非阻塞修复）
        assert self._process.stdout is not None
        response_bytes = await self._process.stdout.readline()
        if not response_bytes:
            raise RuntimeError(
                f"MCP Server {self._server_name} 无响应（stdout 已关闭）"
            )

        response = json.loads(response_bytes.decode().strip())
        if "error" in response:
            raise RuntimeError(
                f"MCP Error from {self._server_name}: {response['error']}"
            )
        return response.get("result", {})

    async def _send_notification(self, method: str, params: dict) -> None:
        """发送 JSON-RPC notification（无 id，不期望 response）。

        Args:
            method: 通知方法名（如 "notifications/initialized", "exit"）
            params: 参数 dict
        """
        if self._process is None:
            return
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()


# ---------------------------------------------------------------------------
# MCPToolWrapper — 将 MCP 工具包装为 BaseTool，注册到 ToolRegistry
# ---------------------------------------------------------------------------


class MCPToolWrapper(BaseTool):
    """将 MCP 工具包装为 BaseTool，注册到 ToolRegistry（ADR-046 第二通道）。

    工具名称格式：mcp__{server_name}__{tool_name}
    遵循 DOC-01 v4 §9 的 MCP 命名空间约定。

    execute() 委托给 MCPClient.call_tool()，返回文本内容。
    ADR-047: MCPToolWrapper 携带 mcp_server 标签（通过工具名命名空间体现），
             filter_tools_for_agent() 阶段按 AgentDefinition.mcp_servers 白名单过滤。
    """

    # MCP 工具不需要特殊 capability（由 mcp_servers 白名单控制）
    capabilities: list[str] = []

    def __init__(
        self,
        server_name: str,
        mcp_tool: dict,
        client: "MCPClient",
    ) -> None:
        """初始化 MCP 工具包装器。

        Args:
            server_name: MCP Server 名称（用于构造工具名命名空间）
            mcp_tool:    MCP Server 返回的工具描述字典
                         {"name": ..., "description": ..., "inputSchema": {...}}
            client:      对应的 MCPClient 实例（用于执行工具调用）
        """
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._client = client

    @property
    def name(self) -> str:
        """工具名称：mcp__{server_name}__{tool_name}（ADR-046 命名空间）"""
        return f"mcp__{self._server_name}__{self._mcp_tool['name']}"

    @property
    def description(self) -> str:
        """ADR-046 第二通道：Tool instructions 通过此 description 进入 tool_grammar_section。"""
        return self._mcp_tool.get("description", "")

    @property
    def input_schema(self) -> dict:
        """工具输入 JSON Schema（来自 MCP Server 的 inputSchema 字段）。"""
        return self._mcp_tool.get("inputSchema", {"type": "object", "properties": {}})

    async def execute(self, tool_input: dict) -> ToolResult:
        """执行 MCP 工具调用，返回 ToolResult。

        委托给 MCPClient.call_tool()，捕获异常转为 is_error=True 的结果。
        """
        try:
            result = await self._client.call_tool(
                self._mcp_tool["name"], tool_input
            )
            return ToolResult(content=result)
        except Exception as exc:
            logger.error(
                "mcp.tool.execute_error",
                tool=self.name,
                error=str(exc),
            )
            return ToolResult(content=str(exc), is_error=True)


# ---------------------------------------------------------------------------
# filter_tools_for_agent — ADR-047 agent-scoped MCP 白名单过滤
# ---------------------------------------------------------------------------


def filter_mcp_tools_for_agent(
    all_clients: list[MCPClient],
    mcp_servers_whitelist: list[str] | None,
) -> list[tuple[str, str]]:
    """按 AgentDefinition.mcp_servers 白名单过滤 MCP 工具对列表。

    ADR-047: agent-scoped MCP 白名单。
    - mcp_servers_whitelist is None: 返回所有 (server_name, tool_name) 对
    - mcp_servers_whitelist 为列表: 只返回白名单内 server 的工具对

    Args:
        all_clients:           所有已启动的 MCPClient 列表
        mcp_servers_whitelist: AgentDefinition.mcp_servers（None=全部允许）

    Returns:
        允许的 (server_name, tool_name) 元组列表

    使用示例：
        pairs = filter_mcp_tools_for_agent(clients, agent_def.mcp_servers)
        # pairs 传给 AgentDefinition.filter_mcp_tools() 的 all_mcp_tools 参数
    """
    all_pairs: list[tuple[str, str]] = []
    for client in all_clients:
        all_pairs.extend(client.list_mcp_tool_pairs())

    if mcp_servers_whitelist is None:
        return all_pairs
    return [(srv, tool) for srv, tool in all_pairs if srv in mcp_servers_whitelist]
