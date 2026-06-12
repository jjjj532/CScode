from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class LSPError(Exception):
    """LSP client errors."""


class LSPClient:
    def __init__(self, server_command: list[str], root_uri: str | None = None) -> None:
        self.server_command = server_command
        self.root_uri = root_uri or f"file://{Path.cwd()}"
        self._process: asyncio.subprocess.Process | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._initialized = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self.is_running:
            return
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise LSPError(f"Failed to start LSP server '{self.server_command[0]}': {e}") from e

        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._writer = self._process.stdin
        self._reader = self._process.stdout
        self._reader_task = asyncio.create_task(self._read_loop())

        _ = await self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": self.root_uri,
                "capabilities": {},
            },
        )
        await self.notify("initialized", {})
        self._initialized = True

    async def stop(self) -> None:
        if self._initialized:
            try:
                await self.notify("shutdown", {})
            except LSPError:
                pass
            self._initialized = False

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, LSPError):
                pass
            self._reader_task = None

        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
            self._writer = None
            self._reader = None

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        if not self.is_running:
            raise LSPError("LSP client not started")
        self._request_id += 1
        req_id = self._request_id
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        await self._send(msg)
        return await future

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.is_running:
            raise LSPError("LSP client not started")
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(msg)

    async def _send(self, msg: dict[str, Any]) -> None:
        if self._writer is None:
            raise LSPError("No transport available")
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        data = (header + body).encode("utf-8")
        self._writer.write(data)
        await self._writer.drain()

    async def _read_loop(self) -> None:
        if self._reader is None:
            return
        try:
            while True:
                result = await self._read_message()
                if result is None:
                    break
                msg_type, req_id, error, result_data = result
                await self._handle_message(msg_type, req_id, error, result_data)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _read_message(self) -> tuple[str, int | None, Any, Any] | None:
        if self._reader is None:
            return None
        header = b""
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            header += line
            if line == b"\r\n":
                break

        content_length = 0
        for h_line in header.decode("utf-8").split("\r\n"):
            if h_line.lower().startswith("content-length:"):
                content_length = int(h_line.split(":")[1].strip())

        body = b""
        while len(body) < content_length:
            chunk = await self._reader.read(content_length - len(body))
            if not chunk:
                return None
            body += chunk

        data = json.loads(body.decode("utf-8"))
        msg_type = (
            "response"
            if "id" in data and "result" in data
            else "error"
            if "id" in data and "error" in data
            else "request"
            if "id" in data
            else "notification"
        )
        return (
            msg_type,
            data.get("id"),
            data.get("error"),
            data.get("result") or data.get("params"),
        )

    async def _handle_message(
        self,
        msg_type: str,
        req_id: int | None,
        error: Any,
        result: Any,
    ) -> None:
        if msg_type in ("response", "error") and req_id is not None:
            future = self._pending.pop(req_id, None)
            if future is not None:
                if error:
                    future.set_exception(LSPError(str(error)))
                else:
                    future.set_result(result)
