from __future__ import annotations

from pathlib import Path
from typing import Any

from cscode.tools.base import BaseTool, ToolResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class ReadTool(BaseTool):
    name = "read"
    description = "Read the contents of a file at the given path"
    requires_permission = False
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

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        path = Path(args["path"])
        logger.debug("ReadTool.execute: path=%s", path)
        if not path.exists():
            logger.warning("ReadTool.execute: file not found path=%s", path)
            return ToolResult(
                success=False,
                data="",
                error=f"File not found: {path}",
            )
        if not path.is_file():
            logger.warning("ReadTool.execute: not a file path=%s", path)
            return ToolResult(
                success=False,
                data="",
                error=f"Not a file: {path}",
            )
        content = path.read_text(encoding="utf-8")
        logger.debug("ReadTool.execute: done path=%s size=%d", path, len(content))
        return ToolResult(
            success=True,
            data=content,
            metadata={"path": str(path), "size": str(len(content))},
        )
