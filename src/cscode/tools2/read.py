"""ReadTool v2 — read file contents with typed output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class ReadInput(BaseModel):
    path: str


class ReadOutput(BaseModel):
    content: str
    size: int
    path: str


class ReadTool(Tool[ReadInput, ReadOutput]):
    name = "read"
    description = "Read the contents of a file at the given path"
    input_schema = ReadInput
    output_schema = ReadOutput

    async def execute(self, input: ReadInput) -> ToolResult[ReadOutput]:
        path = Path(input.path)
        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult(
                success=False,
                error=f"Not a file: {path}",
            )
        content = path.read_text(encoding="utf-8")
        return ToolResult(
            success=True,
            data=ReadOutput(content=content, size=len(content), path=str(path)),
            metadata={"path": str(path), "size": str(len(content))},
        )
