from __future__ import annotations

from typing import Any

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class WebSearchTool(BaseTool):
    name = "websearch"
    description = "Search the web and return results"
    requires_permission = True
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results (default: 8)",
            },
        },
        "required": ["query"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        num_results = args.get("num_results", 8)
        logger.info("WebSearchTool.execute: query=%s num_results=%d", query, num_results)

        return ToolResult(
            success=True,
            data=f"[WebSearch stub] Would search for '{query}' with {num_results} results.",
        )
