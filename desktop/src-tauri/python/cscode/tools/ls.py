from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class LsTool(BaseTool):
    name = "ls"
    description = "List files and directories at the given path"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current working directory)",
            },
        },
        "required": [],
    }

    async def execute(self, args: dict) -> ToolResult:
        path = Path(args.get("path", "."))

        if not path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"Path not found: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                success=False,
                data="",
                error=f"Not a directory: {path}",
            )

        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines: list[str] = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")

        return ToolResult(
            success=True,
            data="\n".join(lines),
            metadata={"count": str(len(entries))},
        )
