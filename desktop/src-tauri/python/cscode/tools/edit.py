from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class EditTool(BaseTool):
    name = "edit"
    description = "Replace text in a file by finding old_string and replacing with new_string"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "Text to find and replace",
            },
            "new_string": {
                "type": "string",
                "description": "Text to replace with",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    async def execute(self, args: dict) -> ToolResult:
        path = Path(args["path"])
        if not path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"File not found: {path}",
            )

        content = path.read_text(encoding="utf-8")
        old = args["old_string"]
        new = args["new_string"]

        if old not in content:
            return ToolResult(
                success=False,
                data="",
                error=f"old_string not found in {path}",
            )

        new_content = content.replace(old, new, 1)
        path.write_text(new_content, encoding="utf-8")
        return ToolResult(
            success=True,
            data=f"Edited {path}",
            metadata={
                "path": str(path),
                "replacement_count": "1",
            },
        )
