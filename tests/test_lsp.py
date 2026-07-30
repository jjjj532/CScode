from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cscode.lsp.client import LSPClient, LSPError

MOCK_LSP = str(Path(__file__).parent / "mock_lsp.py")


def _make_client() -> LSPClient:
    return LSPClient(server_command=["echo"])


@pytest.fixture
async def client():
    c = LSPClient(server_command=["python3", MOCK_LSP])
    await c.start()
    yield c
    await c.stop()


class TestLSPClient:
    async def test_initialization(self):
        client = LSPClient(server_command=["echo"])
        assert client.server_command == ["echo"]

    async def test_invalid_server(self):
        client = LSPClient(server_command=["nonexistent_lsp_server"])
        with pytest.raises(LSPError, match="Failed to start"):
            await client.start()

    async def test_request_before_start(self):
        client = LSPClient(server_command=["echo"])
        with pytest.raises(LSPError, match="not started"):
            await client.request("textDocument/definition", {})

    async def test_notify_before_start(self):
        client = LSPClient(server_command=["echo"])
        with pytest.raises(LSPError, match="not started"):
            await client.notify("textDocument/didOpen", {})

    async def test_stop_without_start(self):
        client = LSPClient(server_command=["echo"])
        await client.stop()


class TestLSPWithMockServer:
    async def test_start_and_stop(self):
        client = LSPClient(server_command=["python3", MOCK_LSP])
        await client.start()
        assert client.is_running
        await client.stop()
        assert not client.is_running

    async def test_double_start(self, client: LSPClient):
        await client.start()
        assert client.is_running

    async def test_definition_request(self, client: LSPClient):
        result = await client.request("textDocument/definition", {
            "textDocument": {"uri": "file:///test.py"},
            "position": {"line": 1, "character": 5},
        })
        assert result is not None
        assert "uri" in result

    async def test_completion_request(self, client: LSPClient):
        result = await client.request("textDocument/completion", {
            "textDocument": {"uri": "file:///test.py"},
            "position": {"line": 0, "character": 0},
        })
        assert result is not None
        assert "items" in result
        labels = [item["label"] for item in result["items"]]
        assert "print" in labels

    async def test_notification(self, client: LSPClient):
        await client.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": "file:///test.py",
                "languageId": "python",
                "version": 1,
                "text": "print('hello')",
            },
        })


class TestLSPReadLoop:
    """Unit tests for _read_loop, _read_message, and _handle_message internals."""

    async def test_read_loop_reader_none(self) -> None:
        """_read_loop returns immediately when _reader is None."""
        client = _make_client()
        assert client._reader is None
        await client._read_loop()

    async def test_read_loop_eof(self) -> None:
        """_read_loop breaks when _read_message returns None (EOF)."""
        client = _make_client()
        reader = asyncio.StreamReader()
        reader.feed_eof()
        client._reader = reader
        await client._read_loop()

    async def test_read_loop_cancelled_error_propagates(self) -> None:
        """CancelledError inside _read_loop is re-raised, not swallowed."""
        client = _make_client()
        client._reader = asyncio.StreamReader()

        async def _mock_read_message() -> None:
            raise asyncio.CancelledError()

        client._read_message = _mock_read_message  # type: ignore[assignment]

        with pytest.raises(asyncio.CancelledError):
            await client._read_loop()

    async def test_read_loop_exception_swallowed(self) -> None:
        """Generic exception in _read_loop is caught by except Exception: pass."""
        client = _make_client()
        client._reader = asyncio.StreamReader()

        async def _mock_read_message() -> None:
            raise ValueError("unexpected")

        client._read_message = _mock_read_message  # type: ignore[assignment]

        await client._read_loop()

    async def test_read_message_full_response(self) -> None:
        """_read_message parses a complete LSP response frame."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"key": "val"}})
        header = f"Content-Length: {len(body)}\r\n\r\n"
        reader.feed_data((header + body).encode("utf-8"))
        client._reader = reader

        result = await client._read_message()
        assert result is not None
        msg_type, req_id, error, result_data = result
        assert msg_type == "response"
        assert req_id == 1
        assert error is None
        assert result_data == {"key": "val"}

    async def test_read_message_eof_during_header(self) -> None:
        """_read_message returns None when reader closes before header completes."""
        client = _make_client()
        reader = asyncio.StreamReader()
        reader.feed_data(b"Content-Length: 5\r\n")
        reader.feed_eof()
        client._reader = reader

        result = await client._read_message()
        assert result is None

    async def test_read_message_classify_response(self) -> None:
        """Message with id+result is classified as 'response'."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"id": 1, "result": {}})
        reader.feed_data(f"Content-Length: {len(body)}\r\n\r\n{body}".encode("utf-8"))
        client._reader = reader

        msg_type, *_ = await client._read_message()  # type: ignore[misc]
        assert msg_type == "response"

    async def test_read_message_classify_error(self) -> None:
        """Message with id+error is classified as 'error'."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"id": 1, "error": {"code": -32601, "message": "method not found"}})
        reader.feed_data(f"Content-Length: {len(body)}\r\n\r\n{body}".encode("utf-8"))
        client._reader = reader

        msg_type, *_ = await client._read_message()  # type: ignore[misc]
        assert msg_type == "error"

    async def test_read_message_classify_request(self) -> None:
        """Message with id but no result/error is classified as 'request'."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"id": 2, "method": "window/showMessageRequest"})
        reader.feed_data(f"Content-Length: {len(body)}\r\n\r\n{body}".encode("utf-8"))
        client._reader = reader

        msg_type, *_ = await client._read_message()  # type: ignore[misc]
        assert msg_type == "request"

    async def test_read_message_classify_notification(self) -> None:
        """Message without id is classified as 'notification'."""
        client = _make_client()
        reader = asyncio.StreamReader()
        body = json.dumps({"method": "textDocument/publishDiagnostics", "params": {}})
        reader.feed_data(f"Content-Length: {len(body)}\r\n\r\n{body}".encode("utf-8"))
        client._reader = reader

        msg_type, *_ = await client._read_message()  # type: ignore[misc]
        assert msg_type == "notification"

    async def test_handle_message_response_resolves_future(self) -> None:
        """_handle_message with response resolves the pending future."""
        client = _make_client()
        future = asyncio.get_event_loop().create_future()
        client._pending[1] = future

        await client._handle_message("response", 1, None, {"key": "val"})
        assert future.done()
        assert future.result() == {"key": "val"}

    async def test_handle_message_error_sets_exception(self) -> None:
        """_handle_message with error sets exception on the pending future."""
        client = _make_client()
        future = asyncio.get_event_loop().create_future()
        client._pending[1] = future

        await client._handle_message("error", 1, {"code": -32601}, None)
        assert future.done()
        with pytest.raises(LSPError):
            future.result()

    async def test_handle_message_unknown_req_id(self) -> None:
        """_handle_message with unknown req_id does not crash."""
        client = _make_client()
        await client._handle_message("response", 99, None, {})

    async def test_handle_message_notification_noop(self) -> None:
        """_handle_message with notification (no req_id) is a no-op."""
        client = _make_client()
        await client._handle_message("notification", None, None, {"diagnostics": []})
