"""GrepTool v2 — search file contents with typed output."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult


class GrepInput(BaseModel):
    pattern: str
    path: str = "."
    include: str | None = None


class GrepOutput(BaseModel):
    matches: int
    files_scanned: int
    output: str


class GrepTool(Tool[GrepInput, GrepOutput]):
    name = "grep"
    description = "Search file contents for a pattern using regex"
    input_schema = GrepInput
    output_schema = GrepOutput

    async def execute(self, input: GrepInput) -> ToolResult[GrepOutput]:
        search_path = Path(input.path)

        if not search_path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {search_path}",
            )

        results: list[str] = []
        files_scanned = 0
        matches_found = 0

        if search_path.is_file():
            files = [search_path]
        else:
            files = sorted(search_path.rglob("*"))

        for file_path in files:
            if not file_path.is_file():
                continue
            if input.include and not fnmatch.fnmatch(file_path.name, input.include):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                files_scanned += 1
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(input.pattern, line):
                        results.append(f"{file_path}:{i}: {line.strip()}")
                        matches_found += 1
                        if matches_found >= 100:
                            break
                if matches_found >= 100:
                    break
            except (OSError, UnicodeDecodeError):
                continue

        output = "\n".join(results)
        summary = f"Found {matches_found} matches in {files_scanned} files."
        full_output = summary + ("\n" + output if output else "")

        return ToolResult(
            success=True,
            data=GrepOutput(matches=matches_found, files_scanned=files_scanned, output=full_output),
            metadata={"matches": str(matches_found), "files_scanned": str(files_scanned)},
        )
