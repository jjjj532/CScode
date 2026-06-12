from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class ReadTool(BaseTool):
    name = "read"
    description = "Read the contents of a file at the given path"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            },
        },
        "required": ["path"],
    }

    async def execute(self, args: dict) -> ToolResult:
        path = Path(args["path"])
        if not path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult(
                success=False,
                data="",
                error=f"Not a file: {path}",
            )
        content = path.read_text(encoding="utf-8")
        return ToolResult(
            success=True,
            data=content,
            metadata={"path": str(path), "size": str(len(content))},
        )
