from __future__ import annotations

from pathlib import Path
from typing import Any

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

# LRU cache for glob results: key = (pattern, path), cleared on each tool call cycle
# Prevents repeated globs (e.g. same pattern from different tool calls) from hitting disk
_glob_cache: dict[tuple[str, str], list[Path]] = {}


def clear_glob_cache() -> None:
    _glob_cache.clear()


def _glob_cached(pattern: str, search_path: Path) -> list[Path]:
    """Glob with in-memory caching per tool-call cycle."""
    key = (pattern, str(search_path.resolve()))
    if key in _glob_cache:
        return _glob_cache[key]
    if "**" not in pattern:
        matches = sorted(search_path.rglob(pattern))
    else:
        matches = sorted(search_path.glob(pattern))
    _glob_cache[key] = matches
    return matches


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

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        pattern = args["pattern"]
        search_path = Path(args.get("path", "."))
        logger.debug("GlobTool.execute: pattern=%s path=%s", pattern, search_path)

        if not search_path.exists():
            return ToolResult(
                success=False,
                data="",
                error=f"Path not found: {search_path}",
            )

        matches = _glob_cached(pattern, search_path)

        if not matches:
            return ToolResult(
                success=True,
                data=f"No files matching '{pattern}' in {search_path}",
                metadata={"count": "0"},
            )

        output = "\n".join(str(m.relative_to(search_path)) for m in matches)
        return ToolResult(
            success=True,
            data=output,
            metadata={"count": str(len(matches))},
        )
