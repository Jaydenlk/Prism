"""Tests for MCPClient HTTP Streamable transport branch."""
import pytest
import httpx
import respx
from executor.plugins.mcp_client import MCPClient


@pytest.mark.asyncio
@respx.mock
async def test_http_init_persists_session_id():
    """Initialize POST → SSE response with Mcp-Session-Id header → client stores it."""
    respx.post("https://mcp.example/mcp").mock(
        return_value=httpx.Response(
            200,
            headers={"Mcp-Session-Id": "session-abc-123", "content-type": "text/event-stream"},
            text=(
                "event: message\n"
                'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"0"}}}\n\n'
            ),
        )
    )
    client = MCPClient(
        server_name="test",
        transport="http",
        url="https://mcp.example/mcp",
        headers={"Authorization": "Bearer x"},
    )
    await client.start()
    assert client.session_id == "session-abc-123"


@pytest.mark.asyncio
@respx.mock
async def test_http_list_tools_parses_sse():
    """list_tools → server returns tools array via SSE → client decodes."""
    route = respx.post("https://mcp.example/mcp")
    route.side_effect = [
        httpx.Response(
            200,
            headers={"Mcp-Session-Id": "s1", "content-type": "text/event-stream"},
            text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}}}\n\n',
        ),
        httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                'event: message\n'
                'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search","description":"x"},{"name":"fetch","description":"y"}]}}\n\n'
            ),
        ),
    ]
    client = MCPClient(server_name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    tools = await client.list_tools()
    names = {t["name"] if isinstance(t, dict) else t.name for t in tools}
    assert names == {"web_search", "fetch"}


@pytest.mark.asyncio
@respx.mock
async def test_http_410_triggers_reinitialize():
    """410 Gone on tool call → client clears session_id + reinitialize + retried call."""
    route = respx.post("https://mcp.example/mcp")
    route.side_effect = [
        # initial init
        httpx.Response(
            200,
            headers={"Mcp-Session-Id": "s-old", "content-type": "text/event-stream"},
            text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}},"tools":[]}\n\n',
        ),
        # 410 on first list_tools call (simulated via a follow-up call)
        httpx.Response(410),
        # reinit after 410
        httpx.Response(
            200,
            headers={"Mcp-Session-Id": "s-new", "content-type": "text/event-stream"},
            text='event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"capabilities":{"tools":{}}}}\n\n',
        ),
        # retried list tools
        httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text='event: message\ndata: {"jsonrpc":"2.0","id":3,"result":{"tools":[]}}\n\n',
        ),
    ]
    client = MCPClient(server_name="test", transport="http", url="https://mcp.example/mcp", headers={})
    await client.start()
    assert client.session_id == "s-old"
    tools = await client.list_tools()
    assert client.session_id == "s-new"
    assert tools == []
