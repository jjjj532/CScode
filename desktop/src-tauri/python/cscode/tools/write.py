from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class WriteTool(BaseTool):
    name = "write"
    description = "Write content to a file, creating or overwriting it"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, args: dict) -> ToolResult:
        path = Path(args["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return ToolResult(
                success=True,
                data=f"Written {len(args['content'])} bytes to {path}",
                metadata={"path": str(path), "size": str(len(args["content"]))},
            )
        except OSError as e:
            return ToolResult(
                success=False,
                data="",
                error=f"Failed to write {path}: {e}",
            )
