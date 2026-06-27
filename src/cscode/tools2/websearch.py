"""WebSearchTool v2 — search the web with typed output."""

from __future__ import annotations

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class WebSearchInput(BaseModel):
    query: str
    num_results: int = 8


class WebSearchOutput(BaseModel):
    results: str


class WebSearchTool(Tool[WebSearchInput, WebSearchOutput]):
    name = "websearch"
    description = "Search the web and return results"
    input_schema = WebSearchInput
    output_schema = WebSearchOutput

    async def execute(self, input: WebSearchInput) -> ToolResult[WebSearchOutput]:
        return ToolResult(
            success=True,
            data=WebSearchOutput(
                results=f"[WebSearch stub] Would search for '{input.query}' with {input.num_results} results."
            ),
        )
