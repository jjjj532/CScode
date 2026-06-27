"""GlobTool v2 — find files matching glob pattern with typed output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class GlobInput(BaseModel):
    pattern: str
    path: str = "."


class GlobOutput(BaseModel):
    matches: list[str]
    count: int


class GlobTool(Tool[GlobInput, GlobOutput]):
    name = "glob"
    description = "Find files matching a glob pattern"
    input_schema = GlobInput
    output_schema = GlobOutput

    async def execute(self, input: GlobInput) -> ToolResult[GlobOutput]:
        search_path = Path(input.path)

        if not search_path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {search_path}",
            )

        matches = sorted(search_path.glob(input.pattern))
        return ToolResult(
            success=True,
            data=GlobOutput(matches=[str(m) for m in matches], count=len(matches)),
            metadata={"count": str(len(matches))},
        )
