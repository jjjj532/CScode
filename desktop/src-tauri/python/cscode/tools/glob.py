from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class GlobTool(BaseTool):
    name = "glob"
    description = "Find files matching a glob pattern"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files (e.g. **/*.py)",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current working directory)",
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, args: dict) -> ToolResult:
        pattern = args["pattern"]
        search_path = Path(args.get("path", "."))

        if not search_path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"Path not found: {search_path}",
            )

        matches = sorted(search_path.glob(pattern))
        if not matches:
            return ToolResult(
                success=True,
                data=f"No files matching '{pattern}' in {search_path}",
                metadata={"count": "0"},
            )

        output = "\n".join(str(m) for m in matches)
        return ToolResult(
            success=True,
            data=output,
            metadata={"count": str(len(matches))},
        )
