"""WebFetchTool v2 — fetch URL content with typed output."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class WebFetchInput(BaseModel):
    url: str
    format: Literal["text", "markdown", "html"] = "markdown"
    timeout: int = 30


class WebFetchOutput(BaseModel):
    content: str
    url: str
    format: str
    size: int


class WebFetchTool(Tool[WebFetchInput, WebFetchOutput]):
    name = "webfetch"
    description = "Fetch content from a URL and return it as formatted text"
    input_schema = WebFetchInput
    output_schema = WebFetchOutput

    async def execute(self, input: WebFetchInput) -> ToolResult[WebFetchOutput]:
        if not input.url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                error=f"Invalid URL: {input.url}",
            )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(input.timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    input.url,
                    headers={"User-Agent": "CScode/1.0"},
                )
                response.raise_for_status()
                content = response.text
                return ToolResult(
                    success=True,
                    data=WebFetchOutput(
                        content=content,
                        url=input.url,
                        format=input.format,
                        size=len(content),
                    ),
                    metadata={"url": input.url, "format": input.format, "size": str(len(content))},
                )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Request failed: {e}",
            )
