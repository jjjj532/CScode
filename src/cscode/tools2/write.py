"""WriteTool v2 — write content to a file with typed output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class WriteInput(BaseModel):
    path: str
    content: str


class WriteOutput(BaseModel):
    path: str
    size: int
    message: str


class WriteTool(Tool[WriteInput, WriteOutput]):
    name = "write"
    description = "Write content to a file, creating or overwriting it"
    input_schema = WriteInput
    output_schema = WriteOutput

    async def execute(self, input: WriteInput) -> ToolResult[WriteOutput]:
        path = Path(input.path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input.content, encoding="utf-8")
            msg = f"Written {len(input.content)} bytes to {path}"
            return ToolResult(
                success=True,
                data=WriteOutput(path=str(path), size=len(input.content), message=msg),
                metadata={"path": str(path), "size": str(len(input.content))},
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error=f"Failed to write {path}: {e}",
            )
