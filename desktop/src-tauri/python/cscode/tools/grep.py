from __future__ import annotations

from pathlib import Path

from cscode.tools.base import BaseTool, ToolResult


class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents for a pattern using regex"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory path to search in (default: current working directory)",
            },
            "include": {
                "type": "string",
                "description": "File pattern to include (e.g. *.py)",
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, args: dict) -> ToolResult:
        pattern = args["pattern"]
        search_path = Path(args.get("path", "."))
        include = args.get("include")

        if not search_path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"Path not found: {search_path}",
            )

        import re

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
            if include:
                import fnmatch

                if not fnmatch.fnmatch(file_path.name, include):
                    continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                files_scanned += 1
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
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
        if output:
            output = summary + "\n" + output
        else:
            output = summary

        return ToolResult(
            success=True,
            data=output,
            metadata={
                "matches": str(matches_found),
                "files_scanned": str(files_scanned),
            },
        )
