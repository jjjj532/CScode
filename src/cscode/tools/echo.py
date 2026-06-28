from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


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
        text = args.get("text", "")
        logger.debug("EchoTool.execute: text_len=%d", len(text))
        return ToolResult(success=True, data=text)
