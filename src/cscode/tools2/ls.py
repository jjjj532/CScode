"""LsTool v2 — list directory contents with typed output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class LsInput(BaseModel):
    path: str = "."


class LsOutput(BaseModel):
    entries: list[str]
    count: int


class LsTool(Tool[LsInput, LsOutput]):
    name = "ls"
    description = "List files and directories at the given path"
    input_schema = LsInput
    output_schema = LsOutput

    async def execute(self, input: LsInput) -> ToolResult[LsOutput]:
        path = Path(input.path)

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                success=False,
                error=f"Not a directory: {path}",
            )

        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines: list[str] = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")

        return ToolResult(
            success=True,
            data=LsOutput(entries=lines, count=len(lines)),
            metadata={"count": str(len(lines))},
        )
