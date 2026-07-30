"""Unit tests for MCPClient._read_loop — JSON-RPC protocol reader."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from cscode.mcp.client import MCPClient


def _json_rpc_msg(data: dict) -> bytes:
    """Build a JSON-RPC message with Content-Length header."""
    body = json.dumps(data).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n"
    return header.encode("utf-8") + body


@pytest.fixture
def mock_reader() -> AsyncMock:
    reader = AsyncMock(spec=asyncio.StreamReader)
    # By default: closed stdin → loop exits immediately
    reader.readline.return_value = b""
    return reader


@pytest.fixture
def client(mock_reader: AsyncMock) -> MCPClient:
    cl = MCPClient(["echo", "test"])
    cl._reader = mock_reader
    return cl


async def _run_read_loop(client: MCPClient) -> asyncio.Task[None]:
    """Run _read_loop as a background task."""
    task = asyncio.create_task(client._read_loop())
    await asyncio.sleep(0)  # let the task start
    return task


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_resolves_pending_future(client: MCPClient, mock_reader: AsyncMock) -> None:
    """A well-formed JSON-RPC response resolves the matching pending future."""
    msg_data = {"jsonrpc": "2.0", "id": 1, "result": {"hello": "world"}}
    wire = _json_rpc_msg(msg_data)
    mock_reader.readline.side_effect = [wire.split(b"\r\n")[0] + b"\r\n", b"\r\n"]
    body = b"\r\n".join(wire.split(b"\r\n")[1:])
    mock_reader.read.return_value = body

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    client._pending[1] = future

    task = await _run_read_loop(client)
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert future.done()
    assert future.result() == {"hello": "world"}


@pytest.mark.asyncio
async def test_read_loop_handles_error_response(client: MCPClient, mock_reader: AsyncMock) -> None:
    """A JSON-RPC error response sets an exception on the pending future."""
    msg_data = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}}
    wire = _json_rpc_msg(msg_data)
    mock_reader.readline.side_effect = [wire.split(b"\r\n")[0] + b"\r\n", b"\r\n"]
    body = b"\r\n".join(wire.split(b"\r\n")[1:])
    mock_reader.read.return_value = body

    from cscode.mcp.client import MCPError

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    client._pending[1] = future

    task = await _run_read_loop(client)
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert future.done()
    assert future.exception() is not None
    assert isinstance(future.exception(), MCPError)


@pytest.mark.asyncio
async def test_read_loop_unknown_id_ignored(client: MCPClient, mock_reader: AsyncMock) -> None:
    """A response with an unknown request id is silently ignored."""
    msg_data = {"jsonrpc": "2.0", "id": 999, "result": {}}
    wire = _json_rpc_msg(msg_data)
    mock_reader.readline.side_effect = [wire.split(b"\r\n")[0] + b"\r\n", b"\r\n", b""]
    body = b"\r\n".join(wire.split(b"\r\n")[1:])
    mock_reader.read.return_value = body

    task = await _run_read_loop(client)
    await asyncio.sleep(0)
    # The loop processes the message (id=999, not in _pending), then reads b"" and exits
    await asyncio.sleep(0)

    # Task should complete (not raise)
    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done
    assert task.exception() is None


@pytest.mark.asyncio
async def test_read_loop_stdin_closed_exits(client: MCPClient, mock_reader: AsyncMock) -> None:
    """When readline returns empty bytes (stdin closed), the loop exits gracefully."""
    mock_reader.readline.return_value = b""

    task = await _run_read_loop(client)
    await asyncio.sleep(0)

    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done
    assert task.exception() is None


@pytest.mark.asyncio
async def test_read_loop_incomplete_body_exits(client: MCPClient, mock_reader: AsyncMock) -> None:
    """When read() returns less than Content-Length, the loop exits gracefully."""
    msg_data = {"jsonrpc": "2.0", "id": 1, "result": "ok"}
    body = json.dumps(msg_data).encode("utf-8")
    header = "Content-Length: 9999\r\n\r\n".encode("utf-8")
    wire = header + body
    mock_reader.readline.side_effect = [wire.split(b"\r\n")[0] + b"\r\n", b"\r\n"]
    mock_reader.read.return_value = body  # shorter than Content-Length 9999

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    client._pending[1] = future

    task = await _run_read_loop(client)
    await asyncio.sleep(0)
    # read() returns body which is shorter than 9999 → loop exits
    await asyncio.sleep(0)

    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done
    assert task.exception() is None
    # Future was never resolved (incomplete body)
    assert not future.done()


@pytest.mark.asyncio
async def test_read_loop_cancelled_propagates(client: MCPClient, mock_reader: AsyncMock) -> None:
    """CancelledError is propagated (not swallowed)."""
    mock_reader.readline.side_effect = asyncio.CancelledError()

    task = asyncio.create_task(client._read_loop())
    await asyncio.sleep(0)

    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done
    # CancelledError makes the task cancelled, not failed
    assert task.cancelled()


@pytest.mark.asyncio
async def test_read_loop_multiple_messages(client: MCPClient, mock_reader: AsyncMock) -> None:
    """Multiple JSON-RPC messages in sequence are all processed."""
    msg1_data = {"jsonrpc": "2.0", "id": 1, "result": "first"}
    msg2_data = {"jsonrpc": "2.0", "id": 2, "result": "second"}

    wire1 = _json_rpc_msg(msg1_data)
    wire2 = _json_rpc_msg(msg2_data)

    # For msg1: header line, blank line, body until Content-Length
    # Simulate two full messages then stdin close
    hdr1 = wire1.split(b"\r\n")[0] + b"\r\n"
    hdr2 = wire2.split(b"\r\n")[0] + b"\r\n"
    body1 = b"\r\n".join(wire1.split(b"\r\n")[1:])
    body2 = b"\r\n".join(wire2.split(b"\r\n")[1:])

    mock_reader.readline.side_effect = [
        hdr1,       # msg1 header line
        b"\r\n",     # msg1 blank line
        hdr2,       # msg2 header line
        b"\r\n",     # msg2 blank line
        b"",         # stdin closed
    ]
    mock_reader.read.side_effect = [body1, body2]

    future1: asyncio.Future = asyncio.get_event_loop().create_future()
    future2: asyncio.Future = asyncio.get_event_loop().create_future()
    client._pending[1] = future1
    client._pending[2] = future2

    task = await _run_read_loop(client)
    # Let the loop process both messages
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # stdin close → loop exits
    await asyncio.sleep(0)

    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done

    assert future1.done()
    assert future1.result() == "first"
    assert future2.done()
    assert future2.result() == "second"


@pytest.mark.asyncio
async def test_read_loop_reader_is_none(client: MCPClient) -> None:
    """When _reader is None, _read_loop returns immediately."""
    client._reader = None
    result = await client._read_loop()
    assert result is None


@pytest.mark.asyncio
async def test_read_loop_content_length_zero(client: MCPClient, mock_reader: AsyncMock) -> None:
    """A message with Content-Length 0 is handled gracefully."""
    mock_reader.readline.side_effect = [
        b"Content-Length: 0\r\n",
        b"\r\n",
        b"",
    ]
    mock_reader.read.return_value = b""

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    client._pending[1] = future

    task = await _run_read_loop(client)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    done, _ = await asyncio.wait([task], timeout=1)
    assert task in done
    # The empty body will fail json.loads, caught by the except clause
    # Future should NOT be resolved
    assert not future.done()
