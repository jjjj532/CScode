from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# Concurrency limit: only 2 concurrent grep operations to avoid IO storms
_grep_semaphore = asyncio.Semaphore(2)

# Result cache: key = (pattern, path, include)
_grep_cache: dict[tuple[str, str, str | None], str] = {}


def clear_grep_cache() -> None:
    _grep_cache.clear()


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

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        pattern = args["pattern"]
        search_path = Path(args.get("path", "."))
        include = args.get("include")
        logger.debug("GrepTool.execute: pattern=%s path=%s include=%s", pattern, search_path, include)

        if not search_path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"Path not found: {search_path}",
            )

        cache_key = (pattern, str(search_path.resolve()), include)
        if cache_key in _grep_cache:
            logger.debug("GrepTool cache hit for %s", cache_key[:2])
            return ToolResult(
                success=True,
                data=_grep_cache[cache_key],
                metadata={"cached": "true"},
            )

        async with _grep_semaphore:
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

            _grep_cache[cache_key] = output

            return ToolResult(
                success=True,
                data=output,
                metadata={
                    "matches": str(matches_found),
                    "files_scanned": str(files_scanned),
                },
            )
