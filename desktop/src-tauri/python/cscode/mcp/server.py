from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from cscode.tools.base import ToolRegistry


class MCPServer:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.tool_schemas = build_tool_schemas(registry)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "cscode-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.tool_schemas},
            }
        elif method == "tools/call":
            return await self._handle_tool_call(req_id, request.get("params", {}))
        elif method in ("notifications/initialized", "shutdown"):
            return {"jsonrpc": "2.0", "id": req_id, "result": None}
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    async def _handle_tool_call(self, req_id: int | None, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool = self.registry.get(name)
        if tool is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{name}' not found"},
            }

        result = await tool.execute(arguments)
        content = []
        if result.success:
            content.append({"type": "text", "text": result.data})
        if result.error:
            content.append({"type": "text", "text": f"Error: {result.error}"})
        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": content}}

    async def run_stdio(self) -> None:
        """Run the MCP server over stdin/stdout."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        while True:
            line = await reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = await self.handle_request(request)
            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()


def build_tool_schemas(registry: ToolRegistry) -> list[dict[str, Any]]:
    schemas = []
    for tool_name in registry.list_tools():
        tool = registry.get(tool_name)
        if tool is None:
            continue
        schemas.append(
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.parameters,
            }
        )
    return schemas
