from __future__ import annotations

import asyncio
import json
from typing import Any


class MCPError(Exception):
    """MCP client errors."""


class MCPClient:
    def __init__(self, server_command: list[str]) -> None:
        self.server_command = server_command
        self._process: asyncio.subprocess.Process | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def connect(self) -> None:
        if self.is_connected:
            return
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise MCPError(f"Failed to start MCP server: {e}") from e

        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._writer = self._process.stdin
        self._reader = self._process.stdout
        self._reader_task = asyncio.create_task(self._read_loop())

        _ = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "cscode", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def disconnect(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, MCPError):
                pass
            self._reader_task = None

        if self._process is not None and self._process.returncode is None:
            try:
                await self._notify("shutdown", {})
            except MCPError:
                pass
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
            self._writer = None
            self._reader = None

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self._request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )
        if "error" in str(result):
            if "not found" in str(result).lower():
                raise MCPError(f"Tool '{name}' not found")
            if "not supported" in str(result).lower():
                raise MCPError(f"Tool '{name}' not supported")
        return result

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        if not self.is_connected:
            raise MCPError("MCP client not connected")
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

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.is_connected:
            raise MCPError("MCP client not connected")
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(msg)

    async def _send(self, msg: dict[str, Any]) -> None:
        if self._writer is None:
            raise MCPError("No transport available")
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._writer.write((header + body).encode("utf-8"))
        await self._writer.drain()

    async def _read_loop(self) -> None:
        if self._reader is None:
            return
        try:
            while True:
                header = b""
                while True:
                    line = await self._reader.readline()
                    if not line:
                        return
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
                        return
                    body += chunk

                data = json.loads(body.decode("utf-8"))
                req_id = data.get("id")
                if req_id is not None:
                    future = self._pending.pop(req_id, None)
                    if future is not None:
                        error = data.get("error")
                        if error:
                            future.set_exception(MCPError(str(error)))
                        else:
                            future.set_result(data.get("result", {}))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
