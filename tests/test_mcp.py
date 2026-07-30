from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cscode.mcp.client import MCPClient, MCPError

MOCK_MCP = str(Path(__file__).parent / "mock_mcp.py")


def _make_client() -> MCPClient:
    return MCPClient(server_command=["echo"])


@pytest.fixture
async def client():
    c = MCPClient(server_command=["python3", MOCK_MCP])
    await c.connect()
    yield c
    await c.disconnect()


class TestMCPClient:
    async def test_connect_and_disconnect(self):
        """启动和关闭 MCP 连接"""
        client = MCPClient(server_command=["python3", MOCK_MCP])
        await client.connect()
        assert client.is_connected
        await client.disconnect()
        assert not client.is_connected

    async def test_list_tools(self, client: MCPClient):
        """列出 MCP 服务器提供的工具"""
        tools = await client.list_tools()
        assert len(tools) > 0
        tool_names = [t["name"] for t in tools]
        assert "read_file" in tool_names
        assert "echo" in tool_names

    async def test_call_tool(self, client: MCPClient):
        """调用 MCP 工具"""
        result = await client.call_tool("echo", {"text": "hello"})
        assert result is not None
        # mock 返回结果

    async def test_call_nonexistent_tool(self, client: MCPClient):
        """调用不存在的工具应该报错"""
        with pytest.raises(MCPError, match="not found"):
            await client.call_tool("nonexistent", {})

    async def test_invalid_server(self):
        """无效的 server 命令报错"""
        client = MCPClient(server_command=["nonexistent_mcp"])
        with pytest.raises(MCPError, match="Failed to start"):
            await client.connect()


class TestMCPReadLoop:
    """Unit tests for _read_loop internals."""

    async def test_read_loop_reader_none(self) -> None:
        """_read_loop returns immediately when _reader is None."""
        client = _make_client()
        assert client._reader is None
        await client._read_loop()

    async def test_read_loop_eof_during_header(self) -> None:
        """_read_loop returns when reader closes during header read."""
        client = _make_client()
        reader = asyncio.StreamReader()
        reader.feed_data(b"Content-Length: 5\r\n")
        reader.feed_eof()
        client._reader = reader
        await client._read_loop()

    async def test_read_loop_eof_during_body(self) -> None:
        """_read_loop returns when reader closes during body read."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        header = f"Content-Length: {len(body) + 100}\r\n\r\n"
        reader.feed_data((header + body).encode("utf-8"))
        reader.feed_eof()
        client._reader = reader
        await client._read_loop()

    async def _feed_one_message(
        self, client: MCPClient, body: dict[str, object]
    ) -> asyncio.StreamReader:
        """Feed one LSP frame into the reader then EOF so _read_loop exits."""
        reader = asyncio.StreamReader()
        payload = json.dumps(body)
        header = f"Content-Length: {len(payload)}\r\n\r\n"
        reader.feed_data((header + payload).encode("utf-8"))
        reader.feed_eof()
        client._reader = reader
        return reader

    async def test_read_loop_resolves_future(self) -> None:
        """_read_loop resolves pending future on successful response."""
        client = _make_client()
        future = asyncio.get_event_loop().create_future()
        client._pending[1] = future
        await self._feed_one_message(client, {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}})

        await client._read_loop()
        assert future.done()
        assert future.result() == {"status": "ok"}

    async def test_read_loop_sets_exception_on_error(self) -> None:
        """_read_loop sets exception on pending future for error response."""
        client = _make_client()
        future = asyncio.get_event_loop().create_future()
        client._pending[1] = future
        await self._feed_one_message(client, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "not found"}})

        await client._read_loop()
        assert future.done()
        with pytest.raises(MCPError, match="not found"):
            future.result()

    async def test_read_loop_unknown_req_id(self) -> None:
        """_read_loop ignores messages with no pending future."""
        client = _make_client()
        await self._feed_one_message(client, {"jsonrpc": "2.0", "id": 99, "result": {}})
        await client._read_loop()

    async def test_read_loop_cancelled_error_propagates(self) -> None:
        """CancelledError in _read_loop is re-raised."""
        client = _make_client()
        client._reader = asyncio.StreamReader()

        async def _mock_readline() -> bytes:
            raise asyncio.CancelledError()

        client._reader.readline = _mock_readline  # type: ignore[assignment]

        with pytest.raises(asyncio.CancelledError):
            await client._read_loop()

    async def test_read_loop_exception_swallowed(self) -> None:
        """Generic exception in _read_loop is caught and logged."""
        client = _make_client()
        client._reader = asyncio.StreamReader()

        async def _mock_readline() -> bytes:
            raise ValueError("unexpected")

        client._reader.readline = _mock_readline  # type: ignore[assignment]

        await client._read_loop()
