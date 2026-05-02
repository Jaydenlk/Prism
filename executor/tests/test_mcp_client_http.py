"""Tests for MCPClient HTTP Streamable transport branch."""
import pytest
import httpx
import respx
from executor.plugins.mcp_client import MCPClient


def _sse_response(payload: str, mcp_session_id: str | None = None, status: int = 200) -> httpx.Response:
    headers: dict[str, str] = {"content-type": "text/event-stream"}
    if mcp_session_id:
        headers["Mcp-Session-Id"] = mcp_session_id
    return httpx.Response(status, headers=headers, text=payload)


@pytest.mark.asyncio
@respx.mock
async def test_http_init_persists_session_id_and_caches_tools():
    """Initialize POST → SSE response with Mcp-Session-Id → client stores it.

    start() also auto-fetches tools/list (parity with stdio start) so two SSE
    responses are needed (init + tools/list).
    """
    route = respx.post("https://mcp.example/mcp")
    route.side_effect = [
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"0"}}}\n\n',
            mcp_session_id="session-abc-123",
        ),
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search"}]}}\n\n',
        ),
    ]
    client = MCPClient(
        server_name="test",
        transport="http",
        url="https://mcp.example/mcp",
        headers={"Authorization": "Bearer x"},
    )
    await client.start()
    assert client.session_id == "session-abc-123"
    # tools cached on start
    assert client.get_tool_definitions() == [{"name": "web_search"}]


@pytest.mark.asyncio
@respx.mock
async def test_http_list_tools_parses_sse():
    """list_tools (live) → SSE response → client decodes tools array.

    start() consumes init + auto-list-tools (2 calls). Then explicit list_tools()
    issues a third call (live request, not cache).
    """
    route = respx.post("https://mcp.example/mcp")
    route.side_effect = [
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}}}\n\n',
            mcp_session_id="s1",
        ),
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search","description":"x"},{"name":"fetch","description":"y"}]}}\n\n',
        ),
        # explicit live list_tools call
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"web_search","description":"x"},{"name":"fetch","description":"y"}]}}\n\n',
        ),
    ]
    client = MCPClient(server_name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    tools = await client.list_tools()
    names = {t["name"] for t in tools}
    assert names == {"web_search", "fetch"}


@pytest.mark.asyncio
@respx.mock
async def test_http_410_triggers_reinitialize():
    """410 Gone on tool call → client clears session_id + reinitialize + retried call.

    Sequence: init → auto-list-tools → external list_tools (410) → reinit (init +
    auto-list-tools) → retried list_tools.
    """
    route = respx.post("https://mcp.example/mcp")
    route.side_effect = [
        # 1: initial init
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}}}\n\n',
            mcp_session_id="s-old",
        ),
        # 2: auto list_tools after init
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n',
        ),
        # 3: external list_tools call → 410
        httpx.Response(410),
        # 4: reinit after 410
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":3,"result":{"capabilities":{"tools":{}}}}\n\n',
            mcp_session_id="s-new",
        ),
        # 5: auto list_tools after reinit
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":4,"result":{"tools":[]}}\n\n',
        ),
        # 6: retried external list_tools
        _sse_response(
            'event: message\ndata: {"jsonrpc":"2.0","id":5,"result":{"tools":[]}}\n\n',
        ),
    ]
    client = MCPClient(server_name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    assert client.session_id == "s-old"
    tools = await client.list_tools()
    assert client.session_id == "s-new"
    assert tools == []
