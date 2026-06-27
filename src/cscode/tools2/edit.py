"""EditTool v2 — replace text in a file with typed output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class EditInput(BaseModel):
    path: str
    old_string: str
    new_string: str


class EditOutput(BaseModel):
    path: str
    replacement_count: int
    message: str


class EditTool(Tool[EditInput, EditOutput]):
    name = "edit"
    description = "Replace text in a file by finding old_string and replacing with new_string"
    input_schema = EditInput
    output_schema = EditOutput

    async def execute(self, input: EditInput) -> ToolResult[EditOutput]:
        path = Path(input.path)
        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )

        content = path.read_text(encoding="utf-8")

        if input.old_string not in content:
            return ToolResult(
                success=False,
                error=f"old_string not found in {path}",
            )

        new_content = content.replace(input.old_string, input.new_string, 1)
        path.write_text(new_content, encoding="utf-8")
        msg = f"Edited {path}"
        return ToolResult(
            success=True,
            data=EditOutput(path=str(path), replacement_count=1, message=msg),
            metadata={"path": str(path), "replacement_count": "1"},
        )
