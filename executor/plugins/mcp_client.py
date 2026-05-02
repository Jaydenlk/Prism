"""
MCP 客户端 — stdio + HTTP Streamable transport

通信协议：
- stdio: asyncio.create_subprocess_exec + JSON-RPC 2.0 over stdin/stdout
- http:  httpx.AsyncClient + POST JSON-RPC + SSE response (MCP spec 2025-03-26)
         Mcp-Session-Id stateful; 410 Gone → re-initialize + retry once

进程边界：本模块只 import 标准库 + executor.tools.*，禁止 import backend.app.*

ADR-046: MCP instructions 双通道注入
ADR-047: agent-scoped MCP 白名单（AgentDefinition.mcp_servers 过滤）
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from executor.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


SCOPE_SYSTEM = "system"
SCOPE_USER = "user"


class MCPClient:
    """MCP Server 客户端，支持 stdio 和 HTTP Streamable transport（ADR-046）。

    scope 二值：
    - "system": 平台级 MCP Server，所有用户可见
    - "user":   用户个人安装，仅对该用户可见
    """

    def __init__(
        self,
        server_name: str,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        scope: str = SCOPE_USER,
        transport: str = "stdio",
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._server_name = server_name
        self._scope = scope
        self.transport = transport

        # stdio fields
        self._command = command or ""
        self._args = args or []
        self._env = env or {}
        self._process: asyncio.subprocess.Process | None = None

        # http fields
        self.url = url
        self.headers = headers or {}
        self.session_id: str | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._next_id = 1

        # shared: cached tools + instructions
        self._tools: list[dict] = []
        self._instructions: str = ""
        self._request_id = 0

    # ------------------------------------------------------------------
    # 生命周期（public dispatch）
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self.transport == "http":
            await self._start_http()
        else:
            await self._start_stdio()

    async def stop(self) -> None:
        if self.transport == "http":
            await self._stop_http()
        else:
            await self._stop_stdio()

    # ------------------------------------------------------------------
    # 工具访问
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[dict]:
        """返回工具列表（stdio 和 http 均在 start() 后填充 self._tools）。"""
        return list(self._tools)

    def get_instructions(self) -> str:
        return self._instructions

    async def list_tools(self) -> list[dict]:
        """Fetch tools from server (HTTP: live request; stdio: return cache)."""
        if self.transport == "http":
            return await self._list_tools_http()
        return list(self._tools)

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def scope(self) -> str:
        return self._scope

    # ------------------------------------------------------------------
    # 工具调用（public dispatch）
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if self.transport == "http":
            return await self._call_tool_http(tool_name, arguments)
        return await self._call_tool_stdio(tool_name, arguments)

    # ------------------------------------------------------------------
    # agent-scoped MCP 白名单过滤（ADR-047）
    # ------------------------------------------------------------------

    def list_mcp_tool_pairs(self) -> list[tuple[str, str]]:
        return [(self._server_name, t["name"]) for t in self._tools]

    # ------------------------------------------------------------------
    # stdio 实现
    # ------------------------------------------------------------------

    async def _start_stdio(self) -> None:
        full_env = {**dict(os.environ), **self._env}
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
        init_result = await self._send_request_stdio(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "prism", "version": "2.0"},
            },
        )
        await self._send_notification_stdio("notifications/initialized", {})
        self._instructions = init_result.get("instructions", "")
        tools_result = await self._send_request_stdio("tools/list", {})
        self._tools = tools_result.get("tools", [])
        logger.info(
            "mcp.client.initialized",
            server_name=self._server_name,
            tool_count=len(self._tools),
            has_instructions=bool(self._instructions),
        )

    async def _stop_stdio(self) -> None:
        if self._process is None:
            return
        try:
            await self._send_request_stdio("shutdown", {})
            await self._send_notification_stdio("exit", {})
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

    async def _call_tool_stdio(self, tool_name: str, arguments: dict) -> str:
        result = await self._send_request_stdio(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        contents = result.get("content", [])
        texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
        return "\n".join(texts)

    async def _send_request_stdio(self, method: str, params: dict) -> dict:
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
        assert self._process.stdin is not None
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()
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

    async def _send_notification_stdio(self, method: str, params: dict) -> None:
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

    # ------------------------------------------------------------------
    # HTTP Streamable transport 实现（MCP spec 2025-03-26）
    # ------------------------------------------------------------------

    async def _start_http(self) -> None:
        """Initialize MCP session over HTTP Streamable transport.

        Closes prior client (if any — re-init path on session expiry) before
        creating a new one to avoid connection/file-descriptor leaks.
        """
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
        self._http_client = httpx.AsyncClient(timeout=30.0)
        await self._http_request({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "prism-executor", "version": "0.1"},
            },
        })
        self._next_id += 1
        # Populate cached tools so get_tool_definitions() works on http transport
        # (parity with stdio behavior post-start). Disable 410 retry to prevent
        # recursive _start_http loop if the new session expires immediately.
        try:
            res = await self._http_request(
                {
                    "jsonrpc": "2.0",
                    "id": self._next_id,
                    "method": "tools/list",
                    "params": {},
                },
                retry_on_410=False,
            )
            self._next_id += 1
            self._tools = (res or {}).get("tools", [])
        except Exception as exc:
            logger.warning("mcp_client.http_list_tools_failed", error=str(exc), server=self._server_name)

    async def _stop_http(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _list_tools_http(self) -> list[dict]:
        res = await self._http_request({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/list",
            "params": {},
        })
        self._next_id += 1
        return (res or {}).get("tools", [])

    async def _call_tool_http(self, tool_name: str, arguments: dict) -> str:
        res = await self._http_request({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        self._next_id += 1
        if res is None:
            return ""
        contents = res.get("content", [])
        texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
        return "\n".join(texts)

    async def _http_request(self, payload: dict, retry_on_410: bool = True) -> Any:
        """Send JSON-RPC over HTTP, stream SSE response, return result.

        Streams the response body (httpx.stream + aiter_lines) so we can return
        as soon as the matching `id` event arrives rather than waiting for full
        body buffering — important for SSE servers that hold the connection open.
        """
        if self._http_client is None:
            raise RuntimeError("HTTP client not started")
        req_headers = dict(self.headers)
        req_headers["Content-Type"] = "application/json"
        req_headers["Accept"] = "application/json, text/event-stream"
        if self.session_id:
            req_headers["Mcp-Session-Id"] = self.session_id

        async with self._http_client.stream(
            "POST", self.url, json=payload, headers=req_headers
        ) as resp:
            if resp.status_code == 410 and retry_on_410:
                # Session expired — drain + close + reinit + retry once
                await resp.aread()
                self.session_id = None
                await self._start_http()
                return await self._http_request(payload, retry_on_410=False)
            resp.raise_for_status()

            new_session = resp.headers.get("Mcp-Session-Id")
            if new_session:
                self.session_id = new_session

            ctype = resp.headers.get("content-type", "")
            expected_id = payload["id"]
            if "text/event-stream" in ctype:
                return await self._consume_sse_stream(resp, expected_id)
            if "application/json" in ctype:
                body = await resp.aread()
                data = json.loads(body)
                return data.get("result") if data.get("id") == expected_id else None
            return None

    async def _consume_sse_stream(self, resp: "httpx.Response", expected_id: int) -> Any:
        """Read SSE frames line-by-line, return first result whose id matches.

        SSE frame format per MCP spec 2025-03-26:
            event: message
            data: {"jsonrpc":"2.0","id":N,"result":{...}}
            <blank>
        Multi-line `data:` is concatenated with newlines.
        """
        data_buf: list[str] = []
        async for line in resp.aiter_lines():
            if line == "":
                # Frame boundary — try to match
                if data_buf:
                    try:
                        msg = json.loads("\n".join(data_buf))
                    except json.JSONDecodeError:
                        msg = None
                    data_buf.clear()
                    if isinstance(msg, dict) and msg.get("id") == expected_id and "result" in msg:
                        return msg["result"]
                continue
            if line.startswith("data:"):
                # SSE spec: "data:" with or without leading space (one SP stripped if present)
                data_buf.append(line[5:].lstrip(" "))
        # Stream ended without matching id
        return None


# ---------------------------------------------------------------------------
# MCPToolWrapper — 将 MCP 工具包装为 BaseTool，注册到 ToolRegistry
# ---------------------------------------------------------------------------


class MCPToolWrapper(BaseTool):
    """将 MCP 工具包装为 BaseTool，注册到 ToolRegistry（ADR-046 第二通道）。

    工具名称格式：mcp__{server_name}__{tool_name}
    """

    capabilities: list[str] = []

    def __init__(
        self,
        server_name: str,
        mcp_tool: dict,
        client: "MCPClient",
    ) -> None:
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._client = client

    @property
    def name(self) -> str:
        return f"mcp__{self._server_name}__{self._mcp_tool['name']}"

    @property
    def description(self) -> str:
        return self._mcp_tool.get("description", "")

    @property
    def input_schema(self) -> dict:
        return self._mcp_tool.get("inputSchema", {"type": "object", "properties": {}})

    async def execute(self, tool_input: dict) -> ToolResult:
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
    """按 AgentDefinition.mcp_servers 白名单过滤 MCP 工具对列表（ADR-047）。"""
    all_pairs: list[tuple[str, str]] = []
    for client in all_clients:
        all_pairs.extend(client.list_mcp_tool_pairs())

    if mcp_servers_whitelist is None:
        return all_pairs
    return [(srv, tool) for srv, tool in all_pairs if srv in mcp_servers_whitelist]
