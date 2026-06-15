from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text back"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to echo"},
        },
        "required": ["text"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data=args.get("text", ""))
