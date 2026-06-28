from __future__ import annotations

from typing import Any

import httpx

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class WebFetchTool(BaseTool):
    name = "webfetch"
    description = "Fetch content from a URL and return it as formatted text"
    requires_permission = True
    permission_default = "allow"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "description": "Output format (default: markdown)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
            },
        },
        "required": ["url"],
    }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        url = args["url"]
        fmt = args.get("format", "markdown")
        timeout = args.get("timeout", 30)
        logger.info("WebFetchTool.execute: url=%s format=%s timeout=%d", url, fmt, timeout)

        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, data="", error=f"Invalid URL: {url}")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "CScode/1.0"})
                response.raise_for_status()
                content = response.text
                return ToolResult(
                    success=True,
                    data=content,
                    metadata={"url": url, "format": fmt, "size": str(len(content))},
                )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, data="", error=f"HTTP {e.response.status_code}: {e}")
        except httpx.RequestError as e:
            return ToolResult(success=False, data="", error=f"Request failed: {e}")
