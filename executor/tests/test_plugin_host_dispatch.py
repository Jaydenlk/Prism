"""Tests for PluginHost dispatching stdio vs http transport."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from executor.plugins.host import PluginHost


def _make_host() -> PluginHost:
    """Create PluginHost with mock dependencies."""
    skill_loader = MagicMock()
    hook_system = MagicMock()
    tool_registry = MagicMock()
    tool_registry.list_definitions.return_value = []
    assembler = MagicMock()
    cc_adapter = MagicMock()
    return PluginHost(skill_loader, hook_system, tool_registry, assembler, cc_adapter)


@pytest.mark.asyncio
async def test_load_stdio_plugin_uses_stdio_branch():
    """Plugin config transport=stdio → MCPClient stdio branch path called."""
    fake_client = MagicMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[])
    fake_client.get_instructions = MagicMock(return_value="")
    with patch("executor.plugins.host.MCPClient") as MockClient:
        MockClient.return_value = fake_client
        host = _make_host()
        await host._start_mcp_server({
            "name": "test",
            "transport": "stdio",
            "command": "echo",
            "args": ["hi"],
            "env": {},
        })
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["transport"] == "stdio"
        assert call_kwargs["command"] == "echo"


@pytest.mark.asyncio
async def test_load_http_plugin_uses_http_branch():
    """Plugin config transport=http → MCPClient http branch path called."""
    fake_client = MagicMock()
    fake_client.start = AsyncMock(return_value=None)
    fake_client.list_tools = AsyncMock(return_value=[])
    fake_client.get_instructions = MagicMock(return_value="")
    with patch("executor.plugins.host.MCPClient") as MockClient:
        MockClient.return_value = fake_client
        host = _make_host()
        await host._start_mcp_server({
            "name": "test",
            "transport": "http",
            "url": "https://mcp.example/mcp",
            "headers": {"Authorization": "Bearer x"},
        })
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["transport"] == "http"
        assert call_kwargs["url"] == "https://mcp.example/mcp"
        assert "Authorization" in call_kwargs["headers"]
